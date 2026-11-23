"""Chat backend tests, run through the real stress-dost app (create_app).

    pip install -r requirements.txt -r requirements-dev.txt
    python -m tests.test_chat
"""
import os, json, base64, time
os.environ.setdefault("OPENAI_API_KEY", "test-not-used")   # stress-dost imports OpenAI at startup
os.environ["MONGODB_URI"] = "mongodb://fake"; os.environ["CHAT_ADMIN_IDS"] = "teacher1,stu2"   # stu2 is listed but a student: never admin
import mongomock
from unittest import mock
from app.chat import mongo
mongo.use_database(mongomock.MongoClient().db)   # in-memory MongoDB
from app import create_app
from app.extensions import socketio
from app.chat import moderation, service as _svc
_svc._SYNC_BACKGROUND = True                     # after-send work runs inline so tests can check it
moderation.settings.OPENAI_API_KEY = ""          # no network in tests

USERS = {"stu1": {"_id":"stu1","name":"Riya","role":"student","reference":"pace","coachingBatch":["apex"],"phone":"9876543210"},
         "stu2": {"_id":"stu2","name":"Aman","role":"student","reference":"pace","coachingBatch":["apex"]},
         "stu3": {"_id":"stu3","name":"Kabir","role":"student","reference":"pace","coachingBatch":[],
                  "meta":{"spartansCourseMathEnrolled":True,"spartansCoursePhysicsEnrolled":False,"parentPhone":"98"}},
         "stu4": {"_id":"stu4","name":"Isha","role":"student","reference":"99+JEE","coachingBatch":[],
                  "meta":{"ioqmJuniorCourseEnrolled":True}},
         "teacher1": {"_id":"teacher1","name":"Anshul Sir","role":"teacher","reference":"pace","coachingBatch":[]},
         "teacher2": {"_id":"teacher2","name":"Neha Ma'am","role":"teacher","reference":"pace","coachingBatch":[]}}
def tok(uid, sig="good"):
    b=lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f'{b({"alg":"HS256"})}.{b({"id":uid,"role":"student","exp":time.time()+3600})}.{sig}'
class R:
    def __init__(s, code, body): s.status_code=code; s._b=body
    def json(s): return s._b
def fake_post(url, json=None, headers=None, timeout=None):
    t=headers["Authorization"].split()[1]
    if not t.endswith("good"): return R(401,{})
    return R(200, {"data": USERS[json["userid"]]})

app = create_app()
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post):
    c = app.test_client()
    H=lambda u: {"Authorization": "Bearer "+tok(u)}
    # bad token
    assert c.get("/api/chat/me", headers={"Authorization":"Bearer "+tok("stu1","bad")}).status_code==401
    # teacher (admin) creates an auto-join announcement group + a chat group
    ann = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Apex Announcements","type":"announcement","batch":"apex","autoJoin":True}).get_json()
    grp = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Apex Doubts","type":"chat","batch":"apex","autoJoin":True}).get_json()
    assert ann["type"]=="announcement" and grp["id"].startswith("g_")
    # students auto-join on connect
    s1 = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu1")})
    s2 = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu2")})
    t1 = socketio.test_client(app, namespace="/chat", auth={"token": tok("teacher1")})
    assert s1.is_connected("/chat") and s2.is_connected("/chat")
    bad = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu1","bad")})
    assert not bad.is_connected("/chat"), "forged token must be refused"
    gl = c.get("/api/chat/groups", headers=H("stu1")).get_json()["groups"]
    assert {g["title"] for g in gl}=={"Apex Announcements","Apex Doubts"}, gl
    # admin sets roll numbers
    c.post(f"/api/chat/groups/{grp['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1","rollNo":"23"}]})
    for x in (s1,s2,t1): x.get_received("/chat")
    # student sends a message
    ack = s1.emit("send", {"groupId": grp["id"], "clientId":"c-1", "text":"Sir, doubt in Q5?"}, namespace="/chat", callback=True)
    assert ack["ok"] and ack["message"]["seq"]==2 and ack["message"]["sender"]["label"]=="Roll 23", ack   # seq 1: "created the group"
    got = [e for e in s2.get_received("/chat") if e["name"]=="message"]
    assert got and (got[0]["args"][0] if isinstance(got[0]["args"],list) else got[0]["args"])["text"]=="Sir, doubt in Q5?"
    # resend same clientId -> same message, no duplicate
    ack2 = s1.emit("send", {"groupId": grp["id"], "clientId":"c-1", "text":"Sir, doubt in Q5?"}, namespace="/chat", callback=True)
    assert ack2["message"]["seq"]==2 and mongo.db().messages.count_documents({"type": "text"})==1
    # student can't post in announcements; teacher can
    a3 = s1.emit("send", {"groupId": ann["id"], "clientId":"c-2", "text":"hi"}, namespace="/chat", callback=True)
    assert not a3["ok"] and a3["error"]=="read_only"
    a4 = t1.emit("send", {"groupId": ann["id"], "clientId":"t-1", "text":"Test on Sunday 9 AM"}, namespace="/chat", callback=True)
    assert a4["ok"] and a4["message"]["sender"]["label"]=="Admin" and a4["message"]["sender"]["avatar"]=="teacher"
    # moderation rules, each on its own (students)
    for text in ["you are a chutiya","join allen instead","call me 98765 43210","see www.example.com",
                 "join my telegram group","f u c k this","FUUUUCK","ch*tiya hai tu".replace("*","u")]:
        v = moderation.check(text, is_staff=False)
        assert not v.allowed, (text, v)
    assert moderation.check("join allen instead", is_staff=True).allowed      # staff may name coachings
    assert moderation.check("Mujhe Q5 mein doubt hai, integration by parts", is_staff=False).allowed
    # 3 blocked messages -> auto restricted in that group
    for i,text in enumerate(["you are a chutiya","join allen instead","call me 98765 43210"]):
        r = s2.emit("send", {"groupId": grp["id"], "clientId":f"m-{i}", "text":text}, namespace="/chat", callback=True)
        assert not r["ok"] and r["error"]=="blocked", (text, r)
    assert mongo.db().moderation.count_documents({"kind":"blocked"})==3
    r = s2.emit("send", {"groupId": grp["id"], "clientId":"ok-1", "text":"normal message"}, namespace="/chat", callback=True)
    assert not r["ok"] and r["error"]=="restricted", r
    # normal words that merely contain banned substrings pass (Scunthorpe check)
    r = s1.emit("send", {"groupId": grp["id"], "clientId":"c-3", "text":"Class at Allenby road? no, the bcc lattice question and mcq"}, namespace="/chat", callback=True)
    assert r["ok"], r
    # history paging + catch-up
    h = c.get(f"/api/chat/groups/{grp['id']}/messages?after=0", headers=H("stu2")).get_json()
    assert [m["seq"] for m in h["messages"]]==[1,2,3] and h["messages"][0]["type"]=="system", h
    h2 = c.get(f"/api/chat/groups/{grp['id']}/messages?after=2", headers=H("stu2")).get_json()
    assert [m["seq"] for m in h2["messages"]]==[3]
    # unread + read receipts
    gl2 = {g["id"]:g for g in c.get("/api/chat/groups", headers=H("stu2")).get_json()["groups"]}
    assert gl2[grp["id"]]["unread"]==3 and gl2[ann["id"]]["unread"]==2
    s2.emit("read", {"groupId": grp["id"], "seq": 3}, namespace="/chat", callback=True)
    gl3 = {g["id"]:g for g in c.get("/api/chat/groups", headers=H("stu2")).get_json()["groups"]}
    assert gl3[grp["id"]]["unread"]==0
    # typing reaches others not sender
    for x in (s1,s2,t1): x.get_received("/chat")
    s1.emit("typing", {"groupId": grp["id"], "typing": True}, namespace="/chat", callback=True)
    assert any(e["name"]=="typing" for e in s2.get_received("/chat"))
    assert not any(e["name"]=="typing" for e in s1.get_received("/chat"))
    # delete own message; others get message_deleted
    d = c.delete(f"/api/chat/groups/{grp['id']}/messages/2", headers=H("stu1")).get_json()
    assert d["ok"]; assert any(e["name"]=="message_deleted" for e in s2.get_received("/chat"))
    assert c.delete(f"/api/chat/groups/{grp['id']}/messages/3", headers=H("stu2")).status_code==403
    # non-member can't read; removed member is dropped
    c.delete(f"/api/chat/groups/{grp['id']}/manage/members/stu2", headers=H("teacher1"))
    assert c.get(f"/api/chat/groups/{grp['id']}/messages", headers=H("stu2")).status_code==403
    # push: device registration + recipients exclude sender, viewers and muted
    sent=[]
    with mock.patch("app.chat.push.send_to_users", side_effect=lambda ids,data: sent.append((list(ids),data))):
        c.post("/api/chat/devices", headers=H("stu1"), json={"token":"fcm-1"})
        s1.emit("viewing", {"groupId": ann["id"]}, namespace="/chat", callback=True)
        t1.emit("send", {"groupId": ann["id"], "clientId":"t-2", "text":"Results out"}, namespace="/chat", callback=True)
        assert sent and "stu1" not in sent[-1][0] and "teacher1" not in sent[-1][0], sent   # stu1 is viewing
        s1.emit("viewing", {"groupId": None}, namespace="/chat", callback=True)
        t1.emit("send", {"groupId": ann["id"], "clientId":"t-3", "text":"Next class 5 PM"}, namespace="/chat", callback=True)
        assert "stu1" in sent[-1][0] and sent[-1][1]["body"].startswith("Anshul Sir:")
        c.post(f"/api/chat/groups/{ann['id']}/mute", headers=H("stu1"), json={"muted": True})
        t1.emit("send", {"groupId": ann["id"], "clientId":"t-4", "text":"x"}, namespace="/chat", callback=True)
        assert all("stu1" not in ids for ids,_ in sent[-1:]) , sent[-1]
    # admin tools: find people, batches, switch auto-join off; students can't use them
    found = c.get("/api/chat/admin/users?q=riy", headers=H("teacher1")).get_json()["users"]
    assert [u["id"] for u in found] == ["stu1"], found
    staff = c.get("/api/chat/admin/users?role=staff", headers=H("teacher1")).get_json()["users"]
    assert [u["id"] for u in staff] == ["teacher1"], staff
    assert c.get("/api/chat/admin/batches?coaching=pace", headers=H("teacher1")).get_json()["batches"] == ["apex"]
    assert c.get("/api/chat/admin/users", headers=H("stu1")).status_code == 403
    assert c.get("/api/chat/admin/users", headers=H("stu2")).status_code == 403   # on the list, but a student
    upd = c.patch(f"/api/chat/groups/{grp['id']}/manage", headers=H("teacher1"), json={"autoJoin": False}).get_json()
    assert upd["id"] == grp["id"] and upd["autoJoin"] is False
    # a group for several batches: students join by their meta flags, like notifications
    sp = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Spartans","type":"chat","autoJoin":True,
               "batches":["spartansCourseMathEnrolled","spartansCoursePhysicsEnrolled","spartansCourseChemEnrolled"]}).get_json()
    mine = [x["id"] for x in c.get("/api/chat/groups", headers=H("stu3")).get_json()["groups"]]
    assert sp["id"] in mine, mine
    assert sp["id"] not in [x["id"] for x in c.get("/api/chat/groups", headers=H("stu2")).get_json()["groups"]]
    # students of a batch, from their own meta flags (instant lookup)
    r = c.get("/api/chat/admin/users?role=student&batches=spartansCourseMathEnrolled,titanCourseMathEnrolled&coachings=pace,99%2BJEE",
              headers=H("teacher1")).get_json()["users"]
    assert [u["id"] for u in r] == ["stu3"], r
    # a group across references (ANSHUL-style pace + 99+JEE): students of both join by batch
    io = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"IOQM Jr","type":"chat","autoJoin":True,
               "batches":["ioqmJuniorCourseEnrolled"], "coachings":["PACE","99+JEE"]}).get_json()
    assert io["id"] in [x["id"] for x in c.get("/api/chat/groups", headers=H("stu4")).get_json()["groups"]]
    # roster: the whole coaching with meta flags, so students who never opened the app show up too
    def fake_roster(url, params=None, json=None, headers=None, timeout=None):
        if url.endswith("/user/details"):          # requests.post is one function for both
            return fake_post(url, json=json, headers=headers, timeout=timeout)
        users = [{"_id": "old1", "name": "Old Student", "role": "student", "reference": "99+JEE",
                  "meta": {"titanCourseMathEnrolled": True, "batch": "JEE"}},
                 {"_id": "old2", "name": "Other", "role": "student", "reference": "99+JEE",
                  "meta": {"titanCourseMathEnrolled": False}}]
        return R(200, {"users": users if params["page"] == 1 else [], "totalPages": 1})
    with mock.patch("app.chat.roster.requests.post", side_effect=fake_roster), \
         mock.patch("app.chat.roster.socketio.start_background_task", side_effect=lambda fn, *a: fn(*a)):
        r = c.post("/api/chat/admin/roster/sync", headers=H("teacher1"), json={"coachings": ["99+JEE"]}).get_json()
    assert r["started"] == ["99+JEE"] and r["status"]["99+JEE"]["state"] == "done", r
    assert r["status"]["99+JEE"]["withMeta"] == 2
    found = c.get("/api/chat/admin/users?role=student&batches=titanCourseMathEnrolled&coachings=99%2BJEE",
                  headers=H("teacher1")).get_json()["users"]
    assert [u["id"] for u in found] == ["old1"], found
    # ── avatars: students pick a character, teachers always have the teacher picture ──
    assert c.post("/api/chat/me/avatar", headers=H("stu1"), json={"avatar": "g2"}).get_json()["avatar"] == "g2"
    assert c.post("/api/chat/me/avatar", headers=H("teacher1"), json={"avatar": "g2"}).status_code == 403
    assert c.post("/api/chat/me/avatar", headers=H("stu1"), json={"avatar": "x"}).status_code == 400
    assert c.get("/api/chat/me", headers=H("stu1")).get_json()["avatar"] == "g2"
    h = c.get(f"/api/chat/groups/{grp['id']}/messages?after=0", headers=H("stu1")).get_json()["messages"]
    assert [m["sender"]["avatar"] for m in h if m["sender"]["id"] == "stu1"][0] == "g2"

    # ── roles: only teachers become admins; admins rename and switch "admins only" ──
    G = grp["id"]
    c.get("/api/chat/me", headers=H("teacher2"))                       # teacher2 known to the server
    c.post(f"/api/chat/groups/{G}/manage/members", headers=H("teacher1"), json={"members": [{"userId": "teacher2", "name": "Neha Ma'am", "role": "teacher"}]})
    r = c.post(f"/api/chat/groups/{G}/manage/members/stu1/role", headers=H("teacher1"), json={"role": "admin"})
    assert r.status_code == 403 and r.get_json()["error"] == "teachers_only"
    assert c.post(f"/api/chat/groups/{G}/manage/members/teacher2/role", headers=H("teacher1"), json={"role": "admin"}).status_code == 200
    assert c.patch(f"/api/chat/groups/{G}/manage", headers=H("teacher2"), json={"title": "Apex Doubts 2026"}).get_json()["title"] == "Apex Doubts 2026"
    assert c.patch(f"/api/chat/groups/{G}/manage", headers=H("stu1"), json={"title": "x"}).status_code == 403
    assert c.delete(f"/api/chat/groups/{G}/manage", headers=H("teacher2")).status_code == 403     # only the creator
    assert c.delete(f"/api/chat/groups/{G}/manage/members/teacher1", headers=H("teacher2")).status_code == 403
    c.patch(f"/api/chat/groups/{G}/manage", headers=H("teacher1"), json={"type": "announcement"})
    r = s1.emit("send", {"groupId": G, "clientId": "c-adm", "text": "can I post?"}, namespace="/chat", callback=True)
    assert not r["ok"] and r["error"] == "read_only"
    texts = [m["text"] for m in c.get(f"/api/chat/groups/{G}/messages?after=0", headers=H("stu1")).get_json()["messages"] if m["type"] == "system"]
    assert any("renamed the group" in t for t in texts) and any("only admins can send" in t for t in texts), texts
    assert any("made Neha Ma'am an admin" in t for t in texts), texts
    c.patch(f"/api/chat/groups/{G}/manage", headers=H("teacher1"), json={"type": "chat"})

    # ── deleting: own message any time; admins anyone's, for everyone ──
    r = s1.emit("send", {"groupId": G, "clientId": "c-del", "text": "oops"}, namespace="/chat", callback=True)
    seq = r["message"]["seq"]
    d = c.delete(f"/api/chat/groups/{G}/messages/{seq}", headers=H("teacher2")).get_json()
    assert d["ok"] and d["byAdmin"]
    m = [x for x in c.get(f"/api/chat/groups/{G}/messages?after={seq-1}", headers=H("stu1")).get_json()["messages"] if x["seq"] == seq][0]
    assert m["deleted"] and m["deletedByAdmin"] and m["text"] == ""

    # ── mute a student for a while: they are told and can't send ──
    sent = []
    with mock.patch("app.chat.push.send_to_users", side_effect=lambda ids, data: sent.append((list(ids), data))):
        c.post(f"/api/chat/groups/{G}/manage/members/stu1/restrict", headers=H("teacher1"), json={"minutes": 180})
    assert sent and sent[-1][0] == ["stu1"] and sent[-1][1]["type"] == "chat_admin" and "3 hours" in sent[-1][1]["body"]
    r = s1.emit("send", {"groupId": G, "clientId": "c-mut", "text": "hello"}, namespace="/chat", callback=True)
    assert not r["ok"] and r["error"] == "restricted"
    mine = {x["id"]: x for x in c.get("/api/chat/groups", headers=H("stu1")).get_json()["groups"]}
    assert mine[G]["restrictedUntil"] > 0 and not mine[G]["canPost"]
    c.post(f"/api/chat/groups/{G}/manage/members/stu1/restrict", headers=H("teacher1"), json={"minutes": 0})

    # ── direct chats: students message teachers only; teachers message students ──
    dm = c.post("/api/chat/direct", headers=H("stu1"), json={"userId": "teacher1"}).get_json()
    assert dm["type"] == "direct" and dm["peer"]["id"] == "teacher1" and dm["peer"]["avatar"] == "teacher"
    assert c.post("/api/chat/direct", headers=H("teacher1"), json={"userId": "stu1"}).get_json()["id"] == dm["id"]
    r = c.post("/api/chat/direct", headers=H("stu1"), json={"userId": "stu2"})      # share Apex Announcements
    assert r.status_code == 403 and "not other students" in r.get_json()["message"]
    assert c.post("/api/chat/direct", headers=H("stu1"), json={"userId": "stu3"}).status_code == 403   # no shared group
    cs = c.get("/api/chat/contacts", headers=H("stu1")).get_json()["contacts"]
    assert {x["id"] for x in cs} == {"teacher1", "teacher2"} and all(x["role"] != "student" for x in cs), cs
    sent = []
    with mock.patch("app.chat.push.send_to_users", side_effect=lambda ids, data: sent.append((list(ids), data))):
        r = s1.emit("send", {"groupId": dm["id"], "clientId": "dm-1", "text": "Sir, one doubt"}, namespace="/chat", callback=True)
    assert r["ok"] and sent[-1][0] == ["teacher1"] and sent[-1][1]["title"] == "Riya", sent

    # ── another group's students: add Spartans to IOQM Jr, see where they came from, remove at once ──
    srcs_before = {x["source"] for x in c.get(f"/api/chat/groups/{io['id']}/manage/sources", headers=H("teacher1")).get_json()["sources"]}
    added = c.post(f"/api/chat/groups/{io['id']}/manage/import", headers=H("teacher1"), json={"fromGroupId": sp["id"]}).get_json()["added"]
    assert added == 1
    srcs = {x["source"]: x for x in c.get(f"/api/chat/groups/{io['id']}/manage/sources", headers=H("teacher1")).get_json()["sources"]}
    assert srcs[f"group:{sp['id']}"]["count"] == 1 and srcs[f"group:{sp['id']}"]["title"] == "Spartans"
    r = c.post(f"/api/chat/groups/{io['id']}/manage/sources/remove", headers=H("teacher1"), json={"source": f"group:{sp['id']}"}).get_json()
    assert r["removed"] == 1
    assert "stu3" not in [m["userId"] for m in c.get(f"/api/chat/groups/{io['id']}/manage/members", headers=H("teacher1")).get_json()["members"]]

    # ── new students: auto-add off -> listed as waiting and the admins are told ──
    t = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title": "Titan Maths", "type": "chat", "autoJoin": False,
               "batches": ["titanCourseMathEnrolled"], "coachings": ["99+JEE"]}).get_json()
    cand = c.get(f"/api/chat/groups/{t['id']}/manage/candidates", headers=H("teacher1")).get_json()["students"]
    assert [x["id"] for x in cand] == ["old1"] and cand[0]["usesApp"] is False, cand
    i2 = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title": "IOQM Doubts", "type": "chat", "autoJoin": False,
                "batches": ["ioqmJuniorCourseEnrolled"], "coachings": ["99+JEE"]}).get_json()
    sent = []
    with mock.patch("app.chat.push.send_to_users", side_effect=lambda ids, data: sent.append((list(ids), data))):
        c.get("/api/chat/groups", headers=H("stu4"))
    assert any(d["type"] == "chat_admin" and "IOQM Doubts" in d["body"] and ids == ["teacher1"] for ids, d in sent), sent
    assert i2["id"] not in [x["id"] for x in c.get("/api/chat/groups", headers=H("stu4")).get_json()["groups"]]
    added = c.post(f"/api/chat/groups/{i2['id']}/manage/members", headers=H("teacher1"),
                   json={"members": [{"userId": "stu4", "name": "Isha"}], "source": "batch:ioqmJuniorCourseEnrolled"}).get_json()["added"]
    assert added == 1 and i2["id"] in [x["id"] for x in c.get("/api/chat/groups", headers=H("stu4")).get_json()["groups"]]

    # ── only the creator deletes a group; it disappears for everyone ──
    assert c.delete(f"/api/chat/groups/{i2['id']}/manage", headers=H("teacher1")).status_code == 200
    assert i2["id"] not in [x["id"] for x in c.get("/api/chat/groups", headers=H("stu4")).get_json()["groups"]]
    print("ALL CHAT TESTS PASSED")

# ── speed fixes: delivered from a notification, receipts count only people with the app ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gq = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Receipts","type":"chat","batch":"none-x"}).get_json()
    c.post(f"/api/chat/groups/{gq['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"},{"userId":"stu3"}]})
    mongo.db().users.update_one({"_id":"stu1"},{"$set":{"fcmTokens":[{"token":"x1"}]}}, upsert=True)
    mongo.db().users.update_one({"_id":"teacher1"},{"$set":{"fcmTokens":[{"token":"x2"}]}}, upsert=True)
    mongo.db().users.update_one({"_id":"stu3"},{"$set":{"fcmTokens":[]}}, upsert=True)
    with mock.patch("app.chat.push.send_to_users"):
        sent = c.post(f"/api/chat/groups/{gq['id']}/messages", headers=H("teacher1"), json={"clientId":"rq-1","text":"hello"}).get_json()["message"]
    assert mongo.db().groups.find_one({"_id": gq["id"]})["lastMessage"]["text"]=="hello"
    r = c.post(f"/api/chat/groups/{gq['id']}/delivered", headers=H("stu1"), json={"seq": sent["seq"]})
    assert r.status_code==200
    gdoc = mongo.db().groups.find_one({"_id": gq["id"]})
    assert gdoc["deliveredSeq"]==sent["seq"], gdoc     # stu3 (no app) does not hold it back
    print("SPEED FIX TESTS PASSED")

# ── empty direct chats, leaving, the left list, member profile, pause everywhere ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gz = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Leavers","type":"chat","batch":"none-z"}).get_json()
    gy = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Second","type":"chat","batch":"none-y"}).get_json()
    for gg in (gz, gy):
        c.post(f"/api/chat/groups/{gg['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"},{"userId":"teacher2","role":"teacher"}]})
    # student opens the teacher chat but sends nothing: the teacher must not see it
    mongo.db().groups.delete_many({"_id": {"$regex": "^dm_.*teacher2"}}); mongo.db().members.delete_many({"groupId": {"$regex": "^dm_.*teacher2"}})
    dm = c.post("/api/chat/direct", headers=H("stu1"), json={"userId":"teacher2"}).get_json()
    ids = lambda u: {x["id"] for x in c.get("/api/chat/groups", headers=H(u)).get_json()["groups"]}
    assert dm["id"] not in ids("teacher2") and dm["id"] in ids("stu1")
    c.post(f"/api/chat/groups/{dm['id']}/messages", headers=H("stu1"), json={"clientId":"dm-1","text":"Maam, a doubt"})
    assert dm["id"] in ids("teacher2")
    # profile
    pr = c.get(f"/api/chat/groups/{gz['id']}/manage/members/stu1", headers=H("teacher1")).get_json()
    assert pr["name"]=="Riya" and {x["title"] for x in pr["groups"]} >= {"Leavers","Second"}, pr
    assert c.get(f"/api/chat/groups/{gz['id']}/manage/members/stu1", headers=H("stu1")).status_code==403
    # pause everywhere I am admin
    r = c.post(f"/api/chat/groups/{gz['id']}/manage/members/stu1/restrict", headers=H("teacher1"), json={"minutes":60,"everywhere":True}).get_json()
    assert r["groups"] >= 2, r
    # creator can't leave; student can
    assert c.post(f"/api/chat/groups/{gz['id']}/leave", headers=H("teacher1")).status_code==403
    assert c.post(f"/api/chat/groups/{gz['id']}/leave", headers=H("stu1")).status_code==200
    assert gz["id"] not in ids("stu1")
    left = c.get(f"/api/chat/groups/{gz['id']}/manage/left", headers=H("teacher1")).get_json()["people"]
    assert [x["userId"] for x in left]==["stu1"]
    # a bulk add does not bring them back; "Add back" (one by one) does
    c.post(f"/api/chat/groups/{gz['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"}],"source":"batch:apex"})
    assert gz["id"] not in ids("stu1")
    c.post(f"/api/chat/groups/{gz['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"}],"source":"manual"})
    assert gz["id"] in ids("stu1")
    assert c.get(f"/api/chat/groups/{gz['id']}/manage/left", headers=H("teacher1")).get_json()["people"]==[]
    print("LEAVE / PROFILE / DM TESTS PASSED")

# ── "X added you to Y" reaches the people added ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as sent:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    ga = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Added Note","type":"chat","batch":"none-a"}).get_json()
    sent.reset_mock()
    c.post(f"/api/chat/groups/{ga['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu2"}]})
    notes = [call.args for call in sent.call_args_list if call.args[1].get("kind")=="added"]
    assert notes and notes[0][0]==["stu2"] and "added you to Added Note" in notes[0][1]["body"], sent.call_args_list
    print("ADDED NOTE TEST PASSED")

# ── photos / voice notes / documents (R2) ──
from app.chat import media as _media
_media.R2_ENDPOINT = "https://acc.r2.cloudflarestorage.com"; _media.R2_ACCESS_KEY_ID = "AK"; _media.R2_SECRET_ACCESS_KEY = "SK"; _media.R2_BUCKET = "bkt"
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed, \
     mock.patch.object(_media, "delete") as deleted:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gm = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Media","type":"chat","batch":"none-m"}).get_json()
    c.post(f"/api/chat/groups/{gm['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"}]})
    up = c.post(f"/api/chat/groups/{gm['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"image/jpeg","size":180000}).get_json()
    assert up["key"].startswith(f"g/{gm['id']}/") and up["key"].endswith(".jpg") and "X-Amz-Signature" in up["uploadUrl"], up
    # too big, wrong kind, someone else's group
    assert c.post(f"/api/chat/groups/{gm['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"image/jpeg","size":50*1024*1024}).status_code==400
    assert c.post(f"/api/chat/groups/{gm['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"text/html","size":10}).status_code==400
    assert c.post(f"/api/chat/groups/{gm['id']}/media/upload", headers=H("stu3"), json={"kind":"image","mime":"image/jpeg","size":10}).status_code==403
    # send with the photo (no caption)
    r = c.post(f"/api/chat/groups/{gm['id']}/messages", headers=H("stu1"),
               json={"clientId":"m-1","text":"","media":{"kind":"image","key":up["key"],"mime":"image/jpeg","size":180000,"width":1200,"height":900}}).get_json()
    m = r["message"]
    assert m["media"]["kind"]=="image" and m["media"]["width"]==1200 and "X-Amz-Signature" in m["media"]["url"], m
    assert mongo.db().groups.find_one({"_id": gm["id"]})["lastMessage"]["text"].startswith("📷 Photo")
    assert any("📷 Photo" in call.args[1]["body"] for call in pushed.call_args_list)
    # a key from another group is refused
    bad = c.post(f"/api/chat/groups/{gm['id']}/messages", headers=H("stu1"), json={"clientId":"m-2","text":"x","media":{"kind":"image","key":"g/other/x.jpg","size":10}})
    assert bad.status_code==400
    # history carries the link; deleting removes the file
    hist = c.get(f"/api/chat/groups/{gm['id']}/messages", headers=H("teacher1")).get_json()["messages"]
    assert any(x.get("media") and x["media"]["key"]==up["key"] for x in hist)
    c.delete(f"/api/chat/groups/{gm['id']}/messages/{m['seq']}", headers=H("stu1"))
    deleted.assert_called_with(up["key"])
    # voice note label
    up2 = c.post(f"/api/chat/groups/{gm['id']}/media/upload", headers=H("teacher1"), json={"kind":"audio","mime":"audio/mp4","size":300000}).get_json()
    c.post(f"/api/chat/groups/{gm['id']}/messages", headers=H("teacher1"),
           json={"clientId":"m-3","media":{"kind":"audio","key":up2["key"],"mime":"audio/mp4","size":300000,"durationMs":65000}})
    assert mongo.db().groups.find_one({"_id": gm["id"]})["lastMessage"]["text"].startswith("🎤 Voice note (1:05)")
    # fresh link
    assert c.get(f"/api/chat/groups/{gm['id']}/media/link?key={up2['key']}", headers=H("stu1")).get_json()["ok"]
    print("MEDIA TESTS PASSED")

# ── the AI check runs after delivery and takes a flagged message down ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed, \
     mock.patch("app.chat.moderation.ai_check", return_value=moderation.Verdict(allowed=False, reasons=["ai:harassment"])):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gq2 = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"AI","type":"chat","batch":"none-q"}).get_json()
    c.post(f"/api/chat/groups/{gq2['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"}]})
    pushed.reset_mock()
    r = c.post(f"/api/chat/groups/{gq2['id']}/messages", headers=H("stu1"), json={"clientId":"ai-1","text":"something nasty"}).get_json()
    assert r["ok"]
    doc = mongo.db().messages.find_one({"groupId": gq2["id"], "clientId": "ai-1"})
    assert doc.get("deletedAt") and doc.get("deletedBy")=="moderation"
    types = [c_.args[1].get("type") for c_ in pushed.call_args_list]
    assert "chat_message" in types and "chat_retract" in types, types     # notified at once, then pulled back
    print("AI AFTER-DELIVERY TEST PASSED")

# ── limits from Firebase chatConfig, storage budget, expiry sweep, editing ──
from app.chat import chatconfig as _cfg
_cfg.set_for_tests({"media": {"image": {"maxKB": 500}, "daily": {"student": {"count": 2, "mb": 1}},
                              "studentsCanSend": {"file": False}, "storageLimitGB": 9, "retentionDays": 21},
                    "messages": {"editMinutes": 60}})
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"), \
     mock.patch.object(_media, "delete"), mock.patch.object(_media, "delete_many") as swept:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gl2 = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Limits","type":"chat","batch":"none-l"}).get_json()
    c.post(f"/api/chat/groups/{gl2['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu4"}]})
    cfg = c.get("/api/chat/config", headers=H("stu4")).get_json()
    assert cfg["media"]["image"]["maxKB"]==500 and cfg["messages"]["editMinutes"]==60
    assert c.get("/api/chat/me", headers=H("stu4")).get_json()["config"]["media"]["daily"]["student"]["count"]==2
    up = lambda kind, mime, size, who="stu4": c.post(f"/api/chat/groups/{gl2['id']}/media/upload", headers=H(who), json={"kind":kind,"mime":mime,"size":size})
    r = up("image","image/jpeg",600*1024); assert r.status_code==400 and r.get_json()["error"]=="too_big", r.get_json()
    r = up("file","application/pdf",1000); assert r.status_code==403 and r.get_json()["error"]=="not_allowed"
    assert up("file","application/pdf",1000,"teacher1").status_code==200          # teachers always may
    sent=[]
    for i in range(2):
        t = up("image","image/jpeg",100*1024).get_json()
        sent.append(c.post(f"/api/chat/groups/{gl2['id']}/messages", headers=H("stu4"),
                           json={"clientId":f"lim-{i}","media":{"kind":"image","key":t["key"],"mime":"image/jpeg","size":100*1024}}).get_json()["message"])
    r = up("image","image/jpeg",100*1024); assert r.status_code==429 and r.get_json()["error"]=="daily_limit", r.get_json()
    # storage budget
    before = mongo.db().media_stats.find_one({"_id":"storage"})["bytes"]
    mongo.db().media_stats.update_one({"_id":"storage"}, {"$set":{"bytes": int(9*1024**3)}})
    r = up("image","image/jpeg",10,"teacher1"); assert r.status_code==507 and r.get_json()["error"]=="storage_full"
    mongo.db().media_stats.update_one({"_id":"storage"}, {"$set":{"bytes": before}})
    # expiry: media_out says until when; the sweep removes old files and frees the storage
    assert sent[0]["media"]["expiresAt"] > sent[0]["createdAt"] and not sent[0]["media"]["expired"]
    mongo.db().messages.update_many({"groupId": gl2["id"], "media.key": {"$exists": True}}, {"$inc": {"createdAt": -22*86_400_000}})
    from app.chat import service as _sv
    assert _sv.sweep_expired_media() >= 2
    swept.assert_called()
    hist = c.get(f"/api/chat/groups/{gl2['id']}/messages", headers=H("stu4")).get_json()["messages"]
    old = [x for x in hist if x.get("media")]
    assert old and all(x["media"]["expired"] and x["media"]["url"]=="" for x in old)
    assert mongo.db().media_stats.find_one({"_id":"storage"})["bytes"] == before - 2*100*1024
    # editing: own message, within the window, shown as edited; not after the window; not others'
    m = c.post(f"/api/chat/groups/{gl2['id']}/messages", headers=H("stu4"), json={"clientId":"ed-1","text":"helo"}).get_json()["message"]
    e = c.patch(f"/api/chat/groups/{gl2['id']}/messages/{m['seq']}", headers=H("stu4"), json={"text":"hello"}).get_json()
    assert e["message"]["text"]=="hello" and e["message"]["editedAt"] > 0
    assert c.patch(f"/api/chat/groups/{gl2['id']}/messages/{m['seq']}", headers=H("teacher1"), json={"text":"x"}).status_code==403
    mongo.db().messages.update_one({"groupId": gl2["id"], "seq": m["seq"]}, {"$inc": {"createdAt": -61*60_000}})
    r = c.patch(f"/api/chat/groups/{gl2['id']}/messages/{m['seq']}", headers=H("stu4"), json={"text":"again"})
    assert r.status_code==403 and r.get_json()["error"]=="edit_window"
    print("LIMITS / EXPIRY / EDIT TESTS PASSED")


# ── captions, reactions (+ notification + catch-up), storage guard ──
_cfg.set_for_tests({"media": {"monthlyUploadGB": 9, "storageLimitGB": 9}})
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed, \
     mock.patch.object(_media, "delete"), mock.patch.object(_media, "delete_many") as removed:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gr = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"React","type":"chat","batch":"none-r"}).get_json()
    c.post(f"/api/chat/groups/{gr['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"},{"userId":"stu2"}]})
    # a photo with a caption: the caption is the message text
    t = c.post(f"/api/chat/groups/{gr['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"image/jpeg","size":90000}).get_json()
    assert mongo.db().media_pending.find_one({"_id": t["key"]})
    m = c.post(f"/api/chat/groups/{gr['id']}/messages", headers=H("stu1"),
               json={"clientId":"cap-1","text":"Q5 from today","media":{"kind":"image","key":t["key"],"mime":"image/jpeg","size":90000}}).get_json()["message"]
    assert m["text"]=="Q5 from today" and m["media"]["kind"]=="image" and m["reactions"]==[]
    assert not mongo.db().media_pending.find_one({"_id": t["key"]}), "sent: no longer pending"
    assert mongo.db().groups.find_one({"_id": gr["id"]})["lastMessage"]["text"]=="📷 Photo Q5 from today"
    # the size the upload was signed for counts, not a smaller number the app claims later
    t2 = c.post(f"/api/chat/groups/{gr['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"image/jpeg","size":120000}).get_json()
    m2 = c.post(f"/api/chat/groups/{gr['id']}/messages", headers=H("stu1"),
                json={"clientId":"cap-2","media":{"kind":"image","key":t2["key"],"mime":"image/jpeg","size":5}}).get_json()["message"]
    assert m2["media"]["size"]==120000
    # reactions: add, change, everyone sees it, the author is notified once per reaction
    s2 = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu2")})
    s1 = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu1")})
    s1.get_received("/chat"); pushed.reset_mock()
    a = s2.emit("react", {"groupId": gr["id"], "seq": m["seq"], "emoji": "👍"}, namespace="/chat", callback=True)
    assert a["ok"] and a["reactions"]==[{"userId":"stu2","name":"Aman","emoji":"👍"}], a
    ev = [e for e in s1.get_received("/chat") if e["name"]=="reaction"]
    assert ev and (ev[0]["args"][0] if isinstance(ev[0]["args"], list) else ev[0]["args"])["seq"]==m["seq"]
    calls = [x for x in pushed.call_args_list if x.args[1].get("type")=="chat_reaction"]
    assert len(calls)==1 and calls[0].args[0]==["stu1"] and "reacted 👍 to" in calls[0].args[1]["body"] and "Q5 from today" in calls[0].args[1]["body"], calls
    assert s2.emit("react", {"groupId": gr["id"], "seq": m["seq"], "emoji": "👍"}, namespace="/chat", callback=True)["ok"]
    assert len([x for x in pushed.call_args_list if x.args[1].get("type")=="chat_reaction"])==1, "same emoji again: no change, no push"
    r = c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu2"), json={"emoji":"❤️"}).get_json()
    assert [x["emoji"] for x in r["reactions"]]==["❤️"]
    c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("teacher1"), json={"emoji":"😂"})
    hist = c.get(f"/api/chat/groups/{gr['id']}/messages", headers=H("stu1")).get_json()["messages"]
    mine = [x for x in hist if x["seq"]==m["seq"]][0]
    assert [x["emoji"] for x in mine["reactions"]]==["❤️","😂"] and mine["reactedAt"]>0
    # reacting to my own message: no notification to myself
    pushed.reset_mock()
    c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu1"), json={"emoji":"🙏"})
    assert not [x for x in pushed.call_args_list if x.args[1].get("type")=="chat_reaction"]
    # taking it back: removed for everyone, the author's notification line is pulled
    pushed.reset_mock()
    r = c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu2"), json={"emoji":""}).get_json()
    assert [x["userId"] for x in r["reactions"]]==["teacher1","stu1"]
    pulled = [x for x in pushed.call_args_list if x.args[1].get("type")=="chat_reaction"]
    assert pulled and pulled[0].args[1]["emoji"]=="", pulled
    # text and system notes can't be reactions; strangers can't react
    assert c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu2"), json={"emoji":"ok"}).status_code==400
    assert c.post(f"/api/chat/groups/{gr['id']}/messages/1/react", headers=H("stu2"), json={"emoji":"👍"}).status_code==404
    assert c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu3"), json={"emoji":"👍"}).status_code==403
    # catch-up for a phone that was offline
    since = mine["reactedAt"]
    c.post(f"/api/chat/groups/{gr['id']}/messages/{m2['seq']}/react", headers=H("stu2"), json={"emoji":"😮"})
    cu = c.get(f"/api/chat/groups/{gr['id']}/reactions?since={since}", headers=H("stu1")).get_json()
    seqs = {x["seq"] for x in cu["items"]}
    assert m2["seq"] in seqs and cu["until"] > since and not cu["more"], cu
    # switched off from Firebase
    _cfg.set_for_tests({"messages": {"reactions": False}})
    assert c.post(f"/api/chat/groups/{gr['id']}/messages/{m['seq']}/react", headers=H("stu2"), json={"emoji":"👍"}).status_code==503
    _cfg.set_for_tests({"media": {"monthlyUploadGB": 9, "storageLimitGB": 9}})
    # storage guard: uploads not sent yet count; this month's cap; unsent uploads are cleared; the total is recounted
    from app.chat import service as _sv
    mongo.db().media_stats.update_one({"_id": _sv._month_key()}, {"$set": {"bytes": int(9*1024**3)}}, upsert=True)
    r = c.post(f"/api/chat/groups/{gr['id']}/media/upload", headers=H("teacher1"), json={"kind":"image","mime":"image/jpeg","size":1000})
    assert r.status_code==507 and "month" in r.get_json()["message"], r.get_json()
    mongo.db().media_stats.update_one({"_id": _sv._month_key()}, {"$set": {"bytes": 0}})
    stale = c.post(f"/api/chat/groups/{gr['id']}/media/upload", headers=H("teacher1"), json={"kind":"image","mime":"image/jpeg","size":1000}).get_json()
    mongo.db().media_pending.update_one({"_id": stale["key"]}, {"$inc": {"at": -4*86_400_000}})
    assert _sv.sweep_unsent_uploads() >= 1 and not mongo.db().media_pending.find_one({"_id": stale["key"]})
    assert stale["key"] in removed.call_args.args[0]
    mongo.db().media_stats.update_one({"_id":"storage"}, {"$set":{"bytes": 999_999_999}})
    total = _sv.recount_storage()
    assert total == mongo.db().media_stats.find_one({"_id":"storage"})["bytes"] and total < 999_999_999 and total >= 90000+120000
    print("CAPTION / REACTION / STORAGE GUARD TESTS PASSED")

# ── delivered / read per person ("Message info"), second tick after being offline, online / last seen ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gi = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Info","type":"chat","batch":"none-i"}).get_json()
    c.post(f"/api/chat/groups/{gi['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"},{"userId":"stu2"},{"userId":"stu4"}]})
    for u in ("stu1", "stu2"):                    # stu1 and stu2 have the app; stu4 never opened it
        mongo.db().users.update_one({"_id": u}, {"$set": {"fcmTokens": [{"token": "tok-"+u}]}}, upsert=True)
    mongo.db().users.update_one({"_id": "stu4"}, {"$set": {"fcmTokens": []}}, upsert=True)
    m = c.post(f"/api/chat/groups/{gi['id']}/messages", headers=H("teacher1"), json={"clientId":"inf-1","text":"Test tomorrow"}).get_json()["message"]
    c.post(f"/api/chat/groups/{gi['id']}/delivered", headers=H("stu1"), json={"seq": m["seq"]})
    c.post(f"/api/chat/groups/{gi['id']}/read", headers=H("stu1"), json={"seq": m["seq"]})
    info = c.get(f"/api/chat/groups/{gi['id']}/messages/{m['seq']}/info", headers=H("teacher1")).get_json()
    assert [x["userId"] for x in info["read"]]==["stu1"] and info["read"][0]["at"] >= m["createdAt"], info
    assert {x["userId"] for x in info["waiting"]}=={"stu2","stu4"} and not info["delivered"]
    assert [x["hasApp"] for x in info["waiting"]]==[True, False], info["waiting"]      # with the app first
    # only the sender may look
    assert c.get(f"/api/chat/groups/{gi['id']}/messages/{m['seq']}/info", headers=H("stu1")).status_code==403
    # stu2 was offline (no notification got through); opening the app = connected: second tick
    from app.chat import presence as _pres
    for sid in list(_pres._user_sids.get("stu2", ())):         # stu2's phones from earlier tests: gone
        _pres.disconnected(sid)
    s2 = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu2")})
    info = c.get(f"/api/chat/groups/{gi['id']}/messages/{m['seq']}/info", headers=H("teacher1")).get_json()
    assert [x["userId"] for x in info["delivered"]]==["stu2"] and info["delivered"][0]["at"] > 0, info
    # a later message: delivered time is per message, not just the latest
    m2 = c.post(f"/api/chat/groups/{gi['id']}/messages", headers=H("teacher1"), json={"clientId":"inf-2","text":"Bring the DPP"}).get_json()["message"]
    c.post(f"/api/chat/groups/{gi['id']}/delivered", headers=H("stu2"), json={"seq": m2["seq"]})
    log_ = mongo.db().members.find_one({"groupId": gi["id"], "userId": "stu2"})["deliveredLog"]
    assert len(log_) == 2 and log_[-1][0] == m2["seq"], log_
    # receipts summary only waits for people with the app (stu4 never had it)
    assert mongo.db().groups.find_one({"_id": gi["id"]})["deliveredSeq"] >= m["seq"]
    # people added after a message never count as "waiting" for it
    mongo.db().members.update_one({"groupId": gi["id"], "userId": "stu4"}, {"$set": {"joinedAt": m2["createdAt"] + 60_000}})
    info2 = c.get(f"/api/chat/groups/{gi['id']}/messages/{m2['seq']}/info", headers=H("teacher1")).get_json()
    assert "stu4" not in {x["userId"] for x in info2["waiting"]}
    # online / last seen in a direct chat
    dm = c.post("/api/chat/direct", headers=H("teacher1"), json={"userId": "stu2"}).get_json()
    dmid = dm.get("id") or dm.get("group", {}).get("id")
    pr = c.get(f"/api/chat/groups/{dmid}/presence", headers=H("teacher1")).get_json()
    assert pr["online"] and pr["userId"]=="stu2", pr
    t1 = socketio.test_client(app, namespace="/chat", auth={"token": tok("teacher1")}); t1.get_received("/chat")
    s2.disconnect(namespace="/chat")
    ev = [e for e in t1.get_received("/chat") if e["name"]=="presence"]
    got = (ev[0]["args"][0] if isinstance(ev[0]["args"], list) else ev[0]["args"]) if ev else {}
    assert got.get("userId")=="stu2" and got.get("online") is False and got.get("lastSeen", 0) > 0, ev
    pr = c.get(f"/api/chat/groups/{dmid}/presence", headers=H("teacher1")).get_json()
    assert not pr["online"] and pr["lastSeen"] > 0
    # silent pushes go at normal priority
    pushed.reset_mock()
    with mock.patch("app.chat.moderation.ai_check", return_value=moderation.Verdict(allowed=False, reasons=["ai:x"])):
        c.post(f"/api/chat/groups/{gi['id']}/messages", headers=H("stu1"), json={"clientId":"inf-3","text":"nasty"})
    retract = [x for x in pushed.call_args_list if x.args[1].get("type")=="chat_retract"]
    assert retract and retract[0].kwargs.get("priority")=="normal", retract
    print("MESSAGE INFO / SECOND TICK / ONLINE TESTS PASSED")

# ── students ask to join; admins approve / decline from the notification ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed:
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    # a group for the apex batch, nobody added automatically, asking switched on
    gj = c.post("/api/chat/admin/groups", headers=H("teacher1"),
                json={"title":"Apex Doubt Club","type":"chat","batch":"apex","autoJoin":False,"joinRequests":True}).get_json()
    assert gj["joinRequests"] is True and gj["requestCount"] == 0
    # stu1 / stu2 are apex: they can see it; stu4 (another coaching) can't
    seen = c.get("/api/chat/discover", headers=H("stu1")).get_json()["groups"]
    assert [x["id"] for x in seen if x["id"]==gj["id"]] and not [x for x in seen if x["id"]==gj["id"]][0]["requested"]
    assert gj["id"] not in {x["id"] for x in c.get("/api/chat/discover", headers=H("stu4")).get_json()["groups"]}
    assert c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu4")).status_code == 403
    # asking: the admins get a notification that opens the requests
    pushed.reset_mock()
    assert c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu1")).get_json()["requested"]
    note = [x for x in pushed.call_args_list if x.args[1].get("kind")=="join_request"]
    assert note and note[0].args[0]==["teacher1"] and "asked to join" in note[0].args[1]["body"], note
    assert c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu1")).get_json()["requested"]   # twice = once
    c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu2"))
    mine = [x for x in c.get("/api/chat/groups", headers=H("teacher1")).get_json()["groups"] if x["id"]==gj["id"]][0]
    assert mine["requestCount"] == 2, mine
    assert [x for x in c.get("/api/chat/discover", headers=H("stu1")).get_json()["groups"] if x["id"]==gj["id"]][0]["requested"]
    reqs = c.get(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("teacher1")).get_json()["requests"]
    assert [r["userId"] for r in reqs] == ["stu1", "stu2"]
    assert c.get(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("stu1")).status_code == 403
    # approve stu1: in the group, told, gone from discover; decline stu2: can't ask again today
    r = c.post(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("teacher1"), json={"userIds":["stu1"], "approve": True}).get_json()
    assert r["count"] == 1
    assert gj["id"] in {x["id"] for x in c.get("/api/chat/groups", headers=H("stu1")).get_json()["groups"]}
    assert gj["id"] not in {x["id"] for x in c.get("/api/chat/discover", headers=H("stu1")).get_json()["groups"]}
    assert any(x.args[1].get("kind")=="added" and x.args[0]==["stu1"] for x in pushed.call_args_list)
    c.post(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("teacher1"), json={"userIds":["stu2"], "approve": False})
    again = c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu2"))
    assert again.status_code == 429 and again.get_json()["error"] == "wait"
    mine = [x for x in c.get("/api/chat/groups", headers=H("teacher1")).get_json()["groups"] if x["id"]==gj["id"]][0]
    assert mine["requestCount"] == 0
    # someone who left can ask to come back, and the admin sees that they left
    c.post(f"/api/chat/groups/{gj['id']}/leave", headers=H("stu1"))
    assert c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu1")).get_json()["requested"]
    reqs = c.get(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("teacher1")).get_json()["requests"]
    assert reqs[0]["note"] == "left"
    # cancelling takes it back; switching asking off hides the group
    c.delete(f"/api/chat/groups/{gj['id']}/request", headers=H("stu1"))
    assert c.get(f"/api/chat/groups/{gj['id']}/manage/requests", headers=H("teacher1")).get_json()["requests"] == []
    c.patch(f"/api/chat/groups/{gj['id']}/manage", headers=H("teacher1"), json={"joinRequests": False})
    assert gj["id"] not in {x["id"] for x in c.get("/api/chat/discover", headers=H("stu1")).get_json()["groups"]}
    assert c.post(f"/api/chat/groups/{gj['id']}/request", headers=H("stu1")).status_code == 403
    # members only ever see it in their own list, not under "can join"
    assert all(x["id"] != ann["id"] for x in c.get("/api/chat/discover", headers=H("stu1")).get_json()["groups"])
    print("ASK TO JOIN TESTS PASSED")

# ── teachers and admins see a student's name and phone numbers (to copy) ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    from app.chat import auth as _auth
    _auth._cache.clear()
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gp = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Phones","type":"chat","batch":"none-p"}).get_json()
    c.post(f"/api/chat/groups/{gp['id']}/manage/members", headers=H("teacher1"),
           json={"members":[{"userId":"stu1"},{"userId":"stu3"},{"userId":"teacher2","role":"teacher"}]})
    c.get("/api/chat/me", headers=H("stu1")); c.get("/api/chat/me", headers=H("stu3")); c.get("/api/chat/me", headers=H("teacher2"))
    pr = c.get(f"/api/chat/groups/{gp['id']}/manage/members/stu1", headers=H("teacher1")).get_json()
    assert pr["phone"] == "9876543210" and pr["name"] == "Riya" and pr["canManage"] is True, pr
    pr3 = c.get(f"/api/chat/groups/{gp['id']}/manage/members/stu3", headers=H("teacher1")).get_json()
    assert pr3["parentPhone"] == "", pr3          # "98" is too short to be a number: left out
    # a teacher who isn't an admin of the group sees the details but gets no admin actions
    prt = c.get(f"/api/chat/groups/{gp['id']}/manage/members/stu1", headers=H("teacher2")).get_json()
    assert prt["phone"] == "9876543210" and prt["canManage"] is False, prt
    # students never see each other's numbers
    assert c.get(f"/api/chat/groups/{gp['id']}/manage/members/stu3", headers=H("stu1")).status_code == 403
    # a teacher's own number is never shown
    assert c.get(f"/api/chat/groups/{gp['id']}/manage/members/teacher2", headers=H("teacher1")).get_json()["phone"] == ""
    print("CONTACT DETAILS TESTS PASSED")
