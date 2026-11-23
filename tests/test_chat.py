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
from app.chat import verify as _verify
_real_needs = _verify.needs
_verify.needs = lambda user, device: None         # phone check has its own section at the end

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
    for text in ["you are a chutiya","join allen instead","call me 98765 43210","join chat.whatsapp.com/AbC123",
                 "join my telegram group","f u c k this","FUUUUCK","ch*tiya hai tu".replace("*","u")]:
        v = moderation.check(text, is_staff=False)
        assert not v.allowed, (text, v)
    assert moderation.check("join allen instead", is_staff=True).allowed      # staff may name coachings
    assert moderation.check("Mujhe Q5 mein doubt hai, integration by parts", is_staff=False).allowed
    # other coachings, phone numbers, links: stopped every time, but never a pause
    for i,text in enumerate(["join allen instead","call me 98765 43210","t.me/freenotes","join allen instead"]):
        r = s2.emit("send", {"groupId": grp["id"], "clientId":f"m-{i}", "text":text}, namespace="/chat", callback=True)
        assert not r["ok"] and r["error"]=="blocked", (text, r)
    assert not mongo.db().members.find_one({"groupId": grp["id"], "userId": "stu2"}).get("restrictedUntil")
    # one explicit message: paused 20 minutes in that group (admins can lift it)
    r = s2.emit("send", {"groupId": grp["id"], "clientId":"m-x", "text":"you are a chutiya"}, namespace="/chat", callback=True)
    assert not r["ok"] and r["error"]=="blocked", r
    assert mongo.db().moderation.count_documents({"kind":"blocked"})==5
    paused = mongo.db().members.find_one({"groupId": grp["id"], "userId": "stu2"})["restrictedUntil"]
    assert 19 * 60_000 < paused - int(time.time()*1000) <= 20 * 60_000, paused
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

    # ── new students: auto-add off -> listed under New students (no notification) ──
    t = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title": "Titan Maths", "type": "chat", "autoJoin": False,
               "batches": ["titanCourseMathEnrolled"], "coachings": ["99+JEE"]}).get_json()
    cand = c.get(f"/api/chat/groups/{t['id']}/manage/candidates", headers=H("teacher1")).get_json()["students"]
    assert [x["id"] for x in cand] == ["old1"] and cand[0]["usesApp"] is False, cand
    i2 = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title": "IOQM Doubts", "type": "chat", "autoJoin": False,
                "batches": ["ioqmJuniorCourseEnrolled"], "coachings": ["99+JEE"]}).get_json()
    sent = []
    with mock.patch("app.chat.push.send_to_users", side_effect=lambda ids, data: sent.append((list(ids), data))):
        c.get("/api/chat/groups", headers=H("stu4"))
    assert not any("not in the group yet" in d.get("body", "") for ids, d in sent), sent     # no notification for this
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
    last = mongo.db().groups.find_one({"_id": gq2["id"]})["lastMessage"]
    assert last["deleted"] is True and last["text"] == "This message was deleted", last   # chat list preview too
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
    # a take-down's retract goes at high priority: the notification must vanish at once
    pushed.reset_mock()
    with mock.patch("app.chat.moderation.ai_check", return_value=moderation.Verdict(allowed=False, reasons=["ai:x"])):
        c.post(f"/api/chat/groups/{gi['id']}/messages", headers=H("stu1"), json={"clientId":"inf-3","text":"nasty"})
    retract = [x for x in pushed.call_args_list if x.args[1].get("type")=="chat_retract"]
    assert retract and retract[0].kwargs.get("priority")=="high", retract
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

# ── links: by default everyone may send them (not WhatsApp/Telegram invites); Firebase can make them admins-only ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    _svc._rate.clear()
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    ge = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Links open","type":"chat","batch":"none-ke"}).get_json()
    c.post(f"/api/chat/groups/{ge['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"}]})
    mongo.db().members.update_many({}, {"$unset": {"restrictedUntil": ""}})
    for i, ok_link in enumerate(["notes: https://drive.google.com/file/d/abc", "youtube.com/watch?v=xyz", "zoom.us/j/123"]):
        r = c.post(f"/api/chat/groups/{ge['id']}/messages", headers=H("stu1"), json={"clientId": f"le-{i}", "text": ok_link})
        assert r.status_code == 200, (ok_link, r.get_json())
    for i, bad in enumerate(["join https://chat.whatsapp.com/Kx12", "wa.me/919876543210", "t.me/jeeleaks", "insta pe aao instagram.com/riya"]):
        r = c.post(f"/api/chat/groups/{ge['id']}/messages", headers=H("stu1"), json={"clientId": f"lb-{i}", "text": bad})
        assert r.status_code == 422, (bad, r.get_json())
    assert not mongo.db().members.find_one({"groupId": ge["id"], "userId": "stu1"}).get("restrictedUntil")   # never a pause for these
    assert c.post(f"/api/chat/groups/{ge['id']}/messages", headers=H("stu1"), json={"clientId": "lp", "text": "pornhub.com"}).status_code == 422

# ── links: admins only (Firebase links = "admins"), students and other teachers can't ──
_cfg.set_for_tests({"moderation": {"links": "admins"}})
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    _svc._rate.clear()                                # earlier sections used up the per-minute budget
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gl = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Links","type":"chat","batch":"none-k"}).get_json()
    c.post(f"/api/chat/groups/{gl['id']}/manage/members", headers=H("teacher1"),
           json={"members":[{"userId":"stu1"},{"userId":"teacher2","role":"teacher"}]})
    mongo.db().members.update_many({"userId": "teacher2", "role": "admin"}, {"$set": {"role": "teacher"}})  # teacher2 runs no group
    meet = "Class now: https://meet.google.com/abc-defg-hij"
    r = c.post(f"/api/chat/groups/{gl['id']}/messages", headers=H("teacher1"), json={"clientId":"ln-1","text":meet})
    assert r.status_code == 200 and r.get_json()["message"]["text"] == meet, r.get_json()
    r = c.post(f"/api/chat/groups/{gl['id']}/messages", headers=H("teacher2"), json={"clientId":"ln-2","text":"see www.example.com"})
    assert r.status_code == 422 and r.get_json()["message"] == "Only admins can send links.", r.get_json()
    assert c.post(f"/api/chat/groups/{gl['id']}/messages", headers=H("teacher2"), json={"clientId":"ln-2b","text":"Revise chapter 4"}).status_code == 200
    r = c.post(f"/api/chat/groups/{gl['id']}/messages", headers=H("stu1"), json={"clientId":"ln-3","text":"zoom.us/j/123"})
    assert r.status_code == 422, r.get_json()
    # private chat: the admin's link goes through there too
    dm = c.post("/api/chat/direct", headers=H("teacher1"), json={"userId": "stu1"}).get_json()
    dmid = dm.get("id") or dm.get("group", {}).get("id")
    r = c.post(f"/api/chat/groups/{dmid}/messages", headers=H("teacher1"), json={"clientId":"ln-4","text":meet})
    assert r.status_code == 200, r.get_json()
    # editing a message into a link follows the same rule
    m = c.post(f"/api/chat/groups/{gl['id']}/messages", headers=H("teacher2"), json={"clientId":"ln-5","text":"link soon"}).get_json()["message"]
    assert c.patch(f"/api/chat/groups/{gl['id']}/messages/{m['seq']}", headers=H("teacher2"), json={"text":"https://x.com"}).status_code == 422
    print("ADMIN LINKS TESTS PASSED")
_cfg.set_for_tests({})
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)

# ── Add people: name, else phone; search by phone; no one shows as an id ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    mongo.db().users.update_one({"_id": "nameless1"}, {"$set": {"role": "student", "coaching": "pace", "phone": "9123456789",
                                                                "batches": ["apex"], "name": ""}}, upsert=True)
    found = c.get("/api/chat/admin/users?q=345678", headers=H("teacher1")).get_json()["users"]
    assert any(u["id"] == "nameless1" and u["phone"] == "9123456789" for u in found), found
    allp = c.get("/api/chat/admin/users?q=", headers=H("teacher1")).get_json()["users"]
    has_name = [bool(u["name"]) for u in allp]
    assert allp and has_name == sorted(has_name, reverse=True), has_name        # everyone with a name first
    riya = [u for u in allp if u["id"] == "stu1"]
    assert riya and riya[0]["phone"] == "9876543210"
    teachers = [u for u in allp if u["role"] == "teacher"]
    assert all(t["phone"] == "" for t in teachers)                       # teachers' numbers never listed
    gp2 = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Phones 2","type":"chat","batch":"none-p2"}).get_json()
    c.post(f"/api/chat/groups/{gp2['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"nameless1"},{"userId":"stu1"}]})
    mem = {m["userId"]: m for m in c.get(f"/api/chat/groups/{gp2['id']}/manage/members", headers=H("teacher1")).get_json()["members"]}
    assert mem["nameless1"]["phone"] == "9123456789" and mem["stu1"]["phone"] == "9876543210", mem
    print("ADD PEOPLE NAME / PHONE TESTS PASSED")

# ── add by name, phone (typed any way) or user id; students only from the admin's coachings ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    c.get("/api/chat/me", headers=H("stu1"))                     # saves stu1's phone and its search key
    assert mongo.db().users.find_one({"_id": "stu1"})["phoneDigits"] == "9876543210"
    for typed in ("+91 98765 43210", "098765-43210", "43210", "Riya", "stu1"):
        got = c.get("/api/chat/admin/users", headers=H("teacher1"), query_string={"q": typed, "within": "pace"}).get_json()["users"]
        assert any(u["id"] == "stu1" for u in got), (typed, got)
    # a student of another coaching never shows up (their number would be in the results)
    mongo.db().users.update_one({"_id": "stu4"}, {"$set": {"phone": "9000011111", "phoneDigits": "9000011111"}})
    got = c.get("/api/chat/admin/users", headers=H("teacher1"), query_string={"q": "9000011111", "within": "pace"}).get_json()["users"]
    assert not any(u["id"] == "stu4" for u in got), got
    got = c.get("/api/chat/admin/users", headers=H("teacher1"), query_string={"q": "Isha", "within": "pace"}).get_json()["users"]
    assert not any(u["id"] == "stu4" for u in got), got
    # teachers can be found from anywhere (to add a visiting teacher)
    got = c.get("/api/chat/admin/users", headers=H("teacher1"), query_string={"q": "Neha", "within": "pace"}).get_json()["users"]
    assert any(u["id"] == "teacher2" for u in got), got
    print("SEARCH BY NAME / PHONE / ID TESTS PASSED")

# ── photos and PDFs: nudity / vulgar words found after delivery → taken down (real model, real PDFs) ──
from app.chat import media_scan as _scan
import numpy as _np, cv2 as _cv2

def _tiny_pdf(text):
    content = ("BT /F1 24 Tf 72 720 Td (%s) Tj ET" % text).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)

assert _scan._detector is None, "the model loads only when the first file arrives"
clean = _np.full((900, 700, 3), 235, _np.uint8); _cv2.putText(clean, "Q5: integrate x^2", (40, 200), _cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 2)
ok_jpg = _cv2.imencode(".jpg", clean)[1].tobytes()
r = _scan.check_image(ok_jpg); assert r.allowed and r.checked, r
assert _scan._detector is not None
assert _scan.check_image(b"not an image").checked is False            # unreadable: let through, not a crash
bad_word = moderation.rules()["bannedWords"][0]
assert _scan.check_pdf(_tiny_pdf("Chapter 4 notes, integration by parts")).allowed
r = _scan.check_pdf(_tiny_pdf("notes " + bad_word)); assert not r.allowed and any(x.startswith("pdf_text") for x in r.reasons), r
assert _scan.check_pdf(b"%PDF-1.4 broken").checked is False

with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed, \
     mock.patch.object(_media, "enabled", return_value=True), mock.patch.object(_media, "delete") as deleted, \
     mock.patch.object(_media, "upload_link", return_value="https://r2/up"):
    _svc._rate.clear()
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gs = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Scan","type":"chat","batch":"none-s"}).get_json()
    c.post(f"/api/chat/groups/{gs['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu1"},{"userId":"stu2"}]})
    def send_photo(cid, data):
        t = c.post(f"/api/chat/groups/{gs['id']}/media/upload", headers=H("stu1"), json={"kind":"image","mime":"image/jpeg","size":len(data)}).get_json()
        with mock.patch.object(_media, "read", return_value=data):
            return c.post(f"/api/chat/groups/{gs['id']}/messages", headers=H("stu1"),
                          json={"clientId":cid,"media":{"kind":"image","key":t["key"],"mime":"image/jpeg","size":len(data)}}).get_json()["message"]
    m = send_photo("scan-ok", ok_jpg)
    assert not mongo.db().messages.find_one({"_id": m["id"]}).get("deletedAt"), "a clean photo stays"
    pushed.reset_mock()
    with mock.patch.object(_scan, "_image_hits", return_value=["female_breast_exposed"]):
        m = send_photo("scan-bad", ok_jpg)
    doc = mongo.db().messages.find_one({"_id": m["id"]})
    assert doc.get("deletedAt") and doc.get("deletedBy") == "moderation", doc
    assert deleted.called, "the file is removed from storage"
    assert any(x.args[1].get("type") == "chat_retract" for x in pushed.call_args_list), "pulled from notifications"
    assert mongo.db().moderation.find_one({"groupId": gs["id"], "reasons": "nudity:female_breast_exposed"})
    # a vulgar PDF sent as a file is taken down too (real PDF, real reader)
    pdf = _tiny_pdf("free notes " + bad_word)
    # (stu1 is paused now: the takedown was one strike too many, which is the point)
    assert mongo.db().members.find_one({"groupId": gs["id"], "userId": "stu1"}).get("restrictedUntil", 0) > 0
    t = c.post(f"/api/chat/groups/{gs['id']}/media/upload", headers=H("stu2"), json={"kind":"file","mime":"application/pdf","size":len(pdf),"name":"n.pdf"}).get_json()
    assert "key" in t, t
    with mock.patch.object(_media, "read", return_value=pdf):
        m = c.post(f"/api/chat/groups/{gs['id']}/messages", headers=H("stu2"),
                   json={"clientId":"scan-pdf","media":{"kind":"file","key":t["key"],"mime":"application/pdf","size":len(pdf),"name":"n.pdf"}}).get_json()["message"]
    assert mongo.db().messages.find_one({"_id": m["id"]}).get("deletedAt"), "vulgar PDF taken down"
    # switched off from Firebase: nothing is checked
    _cfg.set_for_tests({"media": {"scan": {"images": False, "documents": False}}})
    mongo.db().members.update_many({"groupId": gs["id"]}, {"$unset": {"restrictedUntil": ""}})
    mongo.db().users.update_many({}, {"$unset": {"strikes": ""}})
    with mock.patch.object(_scan, "_image_hits", return_value=["female_breast_exposed"]):
        m = send_photo("scan-off", ok_jpg)
    assert not mongo.db().messages.find_one({"_id": m["id"]}).get("deletedAt")
    _cfg.set_for_tests({"media": {"scan": {"images": True, "documents": True}}})
    # a photo sent as a "document" with a made-up type is still checked as a photo
    # student documents: PDF / Word / PowerPoint / Excel only
    for name, mime in (("clip.mp4", "video/mp4"), ("app.apk", "application/vnd.android.package-archive"), ("x.zip", "application/zip")):
        r = c.post(f"/api/chat/groups/{gs['id']}/media/upload", headers=H("stu2"), json={"kind":"file","mime":mime,"size":1000,"name":name})
        assert r.status_code == 403, (name, r.get_json())
    assert c.post(f"/api/chat/groups/{gs['id']}/media/upload", headers=H("stu2"),
                  json={"kind":"file","mime":"application/msword","size":1000,"name":"notes.docx"}).status_code == 200
    assert c.post(f"/api/chat/groups/{gs['id']}/media/upload", headers=H("teacher1"),
                  json={"kind":"file","mime":"video/mp4","size":1000,"name":"lecture.mp4"}).status_code == 200    # teachers: any file
    print("PHOTO / PDF CHECK TESTS PASSED")

# what a file really is, from its first bytes
assert _scan.sniff(b"%PDF-1.7 ...") == "pdf" and _scan.sniff(b"\xff\xd8\xff\xe0") == "image"
assert _scan.sniff(b"\x89PNG\r\n\x1a\n") == "image" and _scan.sniff(b"GIF89a") == "image_other"
assert _scan.sniff(b"\x00\x00\x00\x18ftypheic") == "image_other" and _scan.sniff(b"PK\x03\x04") == "other"
import io as _io
from PIL import Image as _Image
_buf = _io.BytesIO(); _Image.new("RGB", (64, 64), (200, 100, 50)).save(_buf, "JPEG"); _jpg = _buf.getvalue()
_g = _io.BytesIO(); _Image.new("RGB", (64, 64), (10, 200, 50)).save(_g, "GIF"); _gif = _g.getvalue()
with mock.patch.object(_media, "enabled", return_value=True), mock.patch.object(_media, "head", side_effect=lambda k, n=32: _jpg[:n]), \
     mock.patch.object(_media, "read", return_value=_jpg), mock.patch.object(_scan, "_image_hits", return_value=["female_breast_exposed"]):
    r = _scan.check_media({"kind": "file", "key": "g/x/a.bin", "mime": "application/octet-stream", "name": "a.bin"}, strict=True)
    assert not r.allowed and r.reasons == ["nudity:female_breast_exposed"], r
with mock.patch.object(_media, "enabled", return_value=True), mock.patch.object(_media, "head", side_effect=lambda k, n=32: _gif[:n]), \
     mock.patch.object(_media, "read", return_value=_gif), mock.patch.object(_scan, "_image_hits", return_value=["female_breast_exposed"]):
    assert not _scan.check_media({"kind": "image", "key": "g/x/a.gif", "mime": "image/gif"}).allowed     # GIF frames checked
with mock.patch.object(_media, "enabled", return_value=True), mock.patch.object(_media, "head", side_effect=lambda k, n=32: b"\x00\x00\x00\x18ftypheic"), \
     mock.patch.object(_media, "read", return_value=b"\x00\x00\x00\x18ftypheic" + b"\x00" * 100):
    assert not _scan.check_media({"kind": "image", "key": "g/x/a.heic", "mime": "image/heic"}, strict=True).allowed   # can't check: out (student)
    assert _scan.check_media({"kind": "image", "key": "g/x/a.heic", "mime": "image/heic"}, strict=False).allowed
assert not moderation.is_explicit(["unchecked"])           # no pause for that

# ── text: Hindi script, hidden letters, Firebase word lists, self-harm alerts, no false alarms ──
def _blocked(t, staff=False):
    return not moderation.check(t, is_staff=staff, ai=False).allowed
for bad in ("तू मादरचोद है", "भोसड़ीके", "भोसडीके", "गाँड", "f*ck you", "ch#tiya", "b**ch", "c___hu__tiya", "bh__dwa", "ch**t", "bh@dwa", "teri maa ki", "send boobs pic"):
    assert _blocked(bad), bad
for fine in ("chod do yaar, kal karte hain", "आज का होमवर्क क्या है?", "sin^2x + cos^2x = 1", "2*3=6 and 4#5", "Q*5 doubt",
             "visible to the naked eye", "Gandhi ji was born in 1869", "integration by parts", "bcc lattice and fcc",
             "Mahatma Gandhi", "class at 5", "the cocktail party effect"):
    assert not _blocked(fine), fine
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)
_cfg.set_for_tests({"moderation": {"extraWords": ["ullu"], "allowWords": ["harami"]}})
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)
assert _blocked("tu ullu hai") and not _blocked("harami"), "Firebase lists apply"
_cfg.set_for_tests({"moderation": {"extraWords": {"0": "gadha"}}})            # as the Firebase console stores lists
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)
assert _blocked("tu gadha hai")
_cfg.set_for_tests({"moderation": {"extraWords": [], "allowWords": []}})
moderation._rules_cache = (0.0, moderation.DEFAULT_RULES)
assert _blocked("harami")
v = moderation.check("I want to die, nothing matters", is_staff=False, ai=False)
assert v.allowed and v.alert, v                       # goes through, admins alerted
assert moderation.check("मैं आत्महत्या करना चाहता हूँ", is_staff=False, ai=False).alert
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed:
    _svc._rate.clear()
    mongo.db().users.update_many({}, {"$unset": {"strikes": ""}})
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    ga = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"Care","type":"chat","batch":"none-c"}).get_json()
    c.post(f"/api/chat/groups/{ga['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu2"}]})
    r = c.post(f"/api/chat/groups/{ga['id']}/messages", headers=H("stu2"), json={"clientId":"care-1","text":"i want to die"})
    assert r.status_code == 200
    alerts = [x for x in pushed.call_args_list if x.args[1].get("kind") == "alert"]
    assert alerts and alerts[0].args[0] == ["teacher1"] and "may need help" in alerts[0].args[1]["body"], alerts
    r = c.post(f"/api/chat/groups/{ga['id']}/messages", headers=H("stu2"), json={"clientId":"care-2","text":"तू चूतिया है"})
    assert r.status_code == 422, r.get_json()
# emoji: explicit ones stopped, ordinary ones (and single fruit) fine; reactions stricter
for bad in ("🖕", "🖕🏽 bhai", "ok 🔞", "🍆💦", "🍑😏", "👅💦", "come 👉👌", "🍆🍑"):
    assert _blocked(bad), bad
for fine in ("💀💀💀", "😂😂", "🍑 is my favourite fruit", "🍆 ki sabzi", "🥵 so hot today", "💦 sweating", "🔥🔥", "😭🙏"):
    assert not _blocked(fine), fine
assert moderation.emoji_hit("🍆", reaction=True) and not moderation.emoji_hit("😂", reaction=True)
assert moderation.is_explicit(["emoji"]) and moderation.is_explicit(["nudity:female_breast_exposed"])
assert not moderation.is_explicit(["competitor"]) and not moderation.is_explicit(["link", "phone"]) and not moderation.is_explicit(["ai:promo"])
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    _svc._rate.clear(); mongo.db().members.update_many({}, {"$unset": {"restrictedUntil": ""}})
    r = c.post(f"/api/chat/groups/{ga['id']}/messages", headers=H("stu2"), json={"clientId":"emo-1","text":"💀 lol"})
    assert r.status_code == 200
    seq = r.get_json()["message"]["seq"]
    assert c.post(f"/api/chat/groups/{ga['id']}/messages/{seq}/react", headers=H("teacher1"), json={"emoji": "🖕"}).status_code == 400
    assert c.post(f"/api/chat/groups/{ga['id']}/messages/{seq}/react", headers=H("teacher1"), json={"emoji": "😂"}).status_code == 200
print("TEXT CHECK TESTS PASSED")

# ── AI check with Groq: batches, take-down, alerts, learning, fallback between models, daily limit ──
from app.chat import ai_review, settings as _settings
class _Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._b, self.headers, self.text = status, body or {}, headers or {}, json.dumps(body or {})
    def json(self): return self._b
def _answer(content, tokens=900):
    return _Resp(200, {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}})
_settings.GROQ_API_KEY = "test-groq"
ai_review._usage.update({"day": "", "models": {}}); ai_review._blocked_until.clear(); ai_review._next_at.clear()
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users") as pushed:
    _svc._rate.clear(); mongo.db().users.update_many({}, {"$unset": {"strikes": ""}})
    mongo.db().members.update_many({}, {"$unset": {"restrictedUntil": ""}})
    c = app.test_client(); H=lambda u: {"Authorization": "Bearer "+tok(u)}
    gx = c.post("/api/chat/admin/groups", headers=H("teacher1"), json={"title":"AIQ","type":"chat","batch":"none-x"}).get_json()
    c.post(f"/api/chat/groups/{gx['id']}/manage/members", headers=H("teacher1"), json={"members":[{"userId":"stu2"}]})
    texts = ["kal ka test kitne baje hai", "send me ur pic without clothes", "cant take this anymore, ending it tonight", "ok"]
    for i, t in enumerate(texts):
        assert c.post(f"/api/chat/groups/{gx['id']}/messages", headers=H("stu2"), json={"clientId": f"gq-{i}", "text": t}).status_code == 200
    assert len(ai_review._queue) == 3, "ok is too short to spend the allowance on"
    c.post(f"/api/chat/groups/{gx['id']}/messages", headers=H("teacher1"), json={"clientId": "gq-t", "text": "teachers are not queued"})
    assert len(ai_review._queue) == 3
    seen = []
    def groq(url, headers=None, json=None, timeout=None):
        seen.append(json)
        if json["model"] == "openai/gpt-oss-safeguard-20b":
            return _Resp(429, {"error": "slow down"}, {"retry-after": "30"})          # first model busy: next one
        return _answer('{"flag":[{"n":2,"type":"sexual","term":"pic without clothes"}],"alert":[3]}')
    pushed.reset_mock()
    with mock.patch("app.chat.ai_review.requests.post", side_effect=groq):
        assert ai_review.flush(force=True) == 0                 # 429: nothing lost, back in the queue
        assert len(ai_review._queue) == 3
        assert ai_review.flush(force=True) == 3
    assert [s["model"] for s in seen] == ["openai/gpt-oss-safeguard-20b", "openai/gpt-oss-20b"]
    sent = __import__("json").loads(seen[1]["messages"][1]["content"])
    assert [m["n"] for m in sent] == [1, 2, 3] and sent[1]["text"] == texts[1]
    m = {d["clientId"]: d for d in mongo.db().messages.find({"groupId": gx["id"]})}
    assert not m["gq-0"].get("deletedAt") and m["gq-1"].get("deletedBy") == "moderation" and not m["gq-2"].get("deletedAt")
    assert mongo.db().ai_terms.find_one({"_id": "pic without clothes"})["count"] == 1
    alerts = [x for x in pushed.call_args_list if x.args[1].get("kind") == "alert"]
    assert alerts and "may need help" in alerts[0].args[1]["body"], pushed.call_args_list
    assert any(x.args[1].get("type") == "chat_retract" for x in pushed.call_args_list)
    st = c.get("/api/chat/admin/ai-check", headers=H("teacher1")).get_json()
    assert st["days"][0]["checked"] == 3 and st["days"][0]["models"]["openai/gpt-oss-20b"]["tok"] == 900, st
    assert st["words"][0]["term"] == "pic without clothes"
    assert c.get("/api/chat/admin/ai-check", headers=H("stu2")).status_code == 403
    # the AI found something sexual: explicit, so the student is paused and the admins are told
    assert mongo.db().members.find_one({"groupId": gx["id"], "userId": "stu2"}).get("restrictedUntil", 0) > time.time()*1000
    autos = [x for x in pushed.call_args_list if x.args[1].get("kind") == "auto_paused"]
    assert autos and autos[0].args[0] == ["teacher1"], pushed.call_args_list
    # the admin lifts it
    assert c.post(f"/api/chat/groups/{gx['id']}/manage/members/stu2/restrict", headers=H("teacher1"), json={"minutes": 0}).status_code == 200
    assert not mongo.db().members.find_one({"groupId": gx["id"], "userId": "stu2"}).get("restrictedUntil")
    # a message edited after sending: the old flagged text isn't acted on
    c.post(f"/api/chat/groups/{gx['id']}/messages", headers=H("stu2"), json={"clientId": "gq-e", "text": "something rude here"})
    seq = mongo.db().messages.find_one({"clientId": "gq-e"})["seq"]
    c.patch(f"/api/chat/groups/{gx['id']}/messages/{seq}", headers=H("stu2"), json={"text": "sorry, fixed it"})
    ai_review._next_at.clear()
    with mock.patch("app.chat.ai_review.requests.post", return_value=_answer('{"flag":[{"n":1,"type":"abuse","term":"rude"}],"alert":[]}')):
        ai_review.flush(force=True)
    e = mongo.db().messages.find_one({"clientId": "gq-e"})
    assert not e.get("deletedAt") and e["text"] == "sorry, fixed it", e
    # every model used up today: messages keep flowing, counted as word-list only
    for mname in ai_review.LIMITS:
        ai_review._usage["models"][mname] = {"req": 1000, "tok": 0}
    c.post(f"/api/chat/groups/{gx['id']}/messages", headers=H("stu2"), json={"clientId": "gq-u", "text": "hello everyone there"})
    with mock.patch("app.chat.ai_review.requests.post") as never:
        ai_review.flush(force=True)
        never.assert_not_called()
    assert not ai_review._queue
    assert mongo.db().ai_stats.find_one({"_id": f"day:{ai_review._today()}"})["unchecked"] >= 1
    # Firebase can switch it off
    _cfg.set_for_tests({"aiCheck": {"enabled": False}})
    ai_review.submit("some long message here", lambda v, t: None)
    assert not ai_review._queue
    _cfg.set_for_tests({})
    # a model that answers with prose around the JSON, or rubbish
    assert ai_review._parse('Sure! {"flag":[],"alert":[]}') == {"flag": [], "alert": []}
    assert ai_review._parse("no idea") is None
_settings.GROQ_API_KEY = ""
print("GROQ AI CHECK TESTS PASSED")


# ── phone check: OTP on the first hand-add, again on a new phone; backend groups need none ──
_verify.needs = _real_needs
_verify._ok.clear()
otp_calls = []
def acadza_otp(url, json=None, timeout=None, **kw):
    otp_calls.append((url, json))
    if url.endswith("/phonelogin/send"):
        return _Resp(200, {"isSuccessful": True, "challengeId": "ch-1", "expiresIn": 300, "resendAfter": 60})
    if url.endswith("/phonelogin/verify"):
        ok = json["otp"] == "123456" and json["challengeId"] == "ch-1" and json["phone"] == "9876543210"
        return _Resp(200 if ok else 400, {"isSuccessful": ok})
    return fake_post(url, json=json, timeout=timeout, **kw)      # requests.post is one function for all
_Resp.content = b"x"
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"), \
     mock.patch("app.chat.verify.requests.post", side_effect=acadza_otp):
    c = app.test_client()
    D = lambda u, dev: {"Authorization": "Bearer "+tok(u), "X-Chat-Device": dev}
    mongo.db().users.update_many({}, {"$unset": {"verifiedDevice": "", "otpPending": "", "otpSends": ""}})
    mongo.db().members.update_many({}, {"$unset": {"restrictedUntil": ""}}); _svc._rate.clear()
    # stu1 (has a phone) was added by hand to several groups: OTP needed
    st = c.get("/api/chat/me", headers=D("stu1", "phoneA-1234")).get_json()["verify"]
    assert st["required"] and st["reason"] == "first_add" and st["phone"] == "••••••3210" and st["message"], st
    r = c.get("/api/chat/groups", headers=D("stu1", "phoneA-1234"))
    assert r.status_code == 403 and r.get_json()["error"] == "verify_phone"
    # teachers never
    assert c.get("/api/chat/groups", headers=D("teacher1", "tphone-123")).status_code == 200
    # no device id (an old app): asked to update
    assert c.get("/api/chat/groups", headers={"Authorization": "Bearer "+tok("stu1")}).get_json()["reason"] == "update_app"
    # send + wrong code + right code
    sent = c.post("/api/chat/verify/send", headers=D("stu1", "phoneA-1234")).get_json()
    assert sent["sent"] and sent["phone"] == "••••••3210" and otp_calls[-1][1] == {"phone": "9876543210"}, sent
    assert c.post("/api/chat/verify/check", headers=D("stu1", "phoneA-1234"), json={"otp": "000000"}).get_json()["error"] == "wrong_otp"
    assert c.post("/api/chat/verify/check", headers=D("stu1", "phoneB-9999"), json={"otp": "123456"}).get_json()["error"] == "otp_expired"
    ok = c.post("/api/chat/verify/check", headers=D("stu1", "phoneA-1234"), json={"otp": "123456"}).get_json()
    assert ok["verified"], ok
    assert c.get("/api/chat/groups", headers=D("stu1", "phoneA-1234")).status_code == 200
    # notifications only to the verified phone
    c.post("/api/chat/devices", headers=D("stu1", "phoneA-1234"), json={"token": "tokA"})
    # a new phone: asked again; verifying it switches the old one off
    r = c.get("/api/chat/groups", headers=D("stu1", "phoneB-9999"))
    assert r.status_code == 403 and r.get_json()["reason"] == "new_phone"
    c.post("/api/chat/devices", headers=D("stu1", "phoneB-9999"), json={"token": "tokB"})
    c.post("/api/chat/verify/send", headers=D("stu1", "phoneB-9999"))
    assert c.post("/api/chat/verify/check", headers=D("stu1", "phoneB-9999"), json={"otp": "123456"}).get_json()["verified"]
    assert c.get("/api/chat/groups", headers=D("stu1", "phoneA-1234")).get_json()["reason"] == "new_phone"
    toks = [t["token"] for t in mongo.db().users.find_one({"_id": "stu1"})["fcmTokens"]]
    assert "tokA" not in toks and "tokB" in toks, toks
    # the socket follows the same rule
    s_old = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu1"), "device": "phoneA-1234"})
    assert not s_old.is_connected("/chat")
    s_new = socketio.test_client(app, namespace="/chat", auth={"token": tok("stu1"), "device": "phoneB-9999"})
    assert s_new.is_connected("/chat")
    s_new.disconnect(namespace="/chat")
    # too many OTPs
    mongo.db().users.update_one({"_id": "stu1"}, {"$set": {"otpSends": [int(time.time()*1000)] * 5}, "$unset": {"verifiedDevice": ""}})
    assert c.post("/api/chat/verify/send", headers=D("stu1", "phoneC-0000")).status_code == 429
    # stu4 is only in groups from the backend (auto-join / batch): no OTP; the phone is bound quietly
    mongo.db().members.update_many({"userId": "stu4"}, {"$set": {"sources": ["auto"]}})
    assert c.get("/api/chat/groups", headers=D("stu4", "iphone-77777")).status_code == 200
    assert mongo.db().users.find_one({"_id": "stu4"})["verifiedDevice"]["how"] == "backend"
    _verify._ok.clear()
    assert c.get("/api/chat/groups", headers=D("stu4", "other-88888")).get_json()["reason"] == "new_phone"
    # ...and a later hand-add asks for the OTP once
    _verify._ok.clear()
    gid = mongo.db().members.find_one({"userId": "stu4"})["groupId"]
    mongo.db().members.update_one({"userId": "stu4", "groupId": gid}, {"$set": {"sources": ["manual"]}})
    assert c.get("/api/chat/groups", headers=D("stu4", "iphone-77777")).get_json()["reason"] == "first_add"
    # an account without a phone number is let in (logged)
    mongo.db().users.update_one({"_id": "stu2"}, {"$unset": {"phone": "", "verifiedDevice": ""}})
    _verify._ok.clear()
    if c.get("/api/chat/groups", headers=D("stu2", "aman-phone1")).status_code == 403:
        assert c.post("/api/chat/verify/send", headers=D("stu2", "aman-phone1")).get_json() == {"required": False}
    assert c.get("/api/chat/groups", headers=D("stu2", "aman-phone1")).status_code == 200
print("PHONE CHECK TESTS PASSED")

# ── Firebase switches for everyone: chat closed, app build too old ──
with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client()
    T = lambda u, client="1": {"Authorization": "Bearer "+tok(u), "X-Chat-Device": "tphone-123", "X-Chat-Client": client}
    _cfg.set_for_tests({"service": {"open": False, "closedMessage": "Back at 6 PM"}})
    r = c.get("/api/chat/groups", headers=T("teacher1"))
    assert r.status_code == 403 and r.get_json()["reason"] == "closed" and r.get_json()["message"] == "Back at 6 PM"
    assert c.get("/api/chat/me", headers=T("teacher1")).get_json()["verify"]["reason"] == "closed"
    s_closed = socketio.test_client(app, namespace="/chat", auth={"token": tok("teacher1"), "device": "tphone-123", "client": 1})
    assert not s_closed.is_connected("/chat")
    _cfg.set_for_tests({"service": {"minClientVersion": 2}})
    assert c.get("/api/chat/groups", headers=T("teacher1", "1")).get_json()["reason"] == "update_app"
    assert c.get("/api/chat/groups", headers=T("teacher1", "2")).status_code == 200
    _cfg.set_for_tests({})
    assert c.get("/api/chat/groups", headers=T("teacher1", "")).status_code == 200      # off by default
print("SWITCHES TESTS PASSED")

# ── link previews, teacher photos, Sir / Ma'am, students adding their name ──
from app.chat import linkpreview as _lp
assert _lp.youtube_id("https://youtu.be/dQw4w9WgXcQ?t=3") == "dQw4w9WgXcQ"
assert _lp.youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x") == "dQw4w9WgXcQ"
assert _lp.youtube_id("youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ" and _lp.youtube_id("https://example.com") is None
head = _lp.parse_head('<html><head><title>Fallback</title><meta property="og:title" content="Kinematics &amp; more">'
                      '<meta content="https://cdn.x.com/a.jpg" property="og:image"><meta name="description" content="Notes"></head>')
assert head == {"title": "Kinematics & more", "description": "Notes", "image": "https://cdn.x.com/a.jpg", "site": ""}, head
assert not _lp._public_host("127.0.0.1") and not _lp._public_host("10.0.0.5") and not _lp._public_host("localhost")
class _R:
    def __init__(self, status, body=b"", ctype="text/html", headers=None, j=None):
        self.status_code, self._b, self.headers, self._j = status, body, {"content-type": ctype, **(headers or {})}, j
    def iter_content(self, n): yield self._b
    def close(self): pass
    def json(self): return self._j
def fake_get(url, headers=None, timeout=None, stream=False, allow_redirects=True, params=None):
    if "oembed" in url: return _R(200, j={"title": "Projectile motion in 10 min", "author_name": "Physics Sir"})
    if url.endswith(".jpg"): return _R(200, b"img", "image/jpeg")
    if "adult" in url: return _R(200, b'<meta property="og:title" content="hot pics"><meta property="og:image" content="https://adult.example/n.jpg">')
    return _R(200, b'<meta property="og:title" content="NCERT Physics"><meta property="og:image" content="/cover.jpg">')
with mock.patch("app.chat.linkpreview.requests.get", side_effect=fake_get), mock.patch.object(_lp, "_public_host", return_value=True), \
     mock.patch.object(_scan, "check_image", side_effect=lambda d: _scan.ScanResult(allowed=True)):
    yt = _lp.preview("https://youtu.be/dQw4w9WgXcQ")
    assert yt["video"] and yt["title"] == "Projectile motion in 10 min" and yt["image"].endswith("/hqdefault.jpg"), yt
    pg = _lp.preview("https://ncert.example/book")
    assert pg["title"] == "NCERT Physics" and pg["image"] == "https://ncert.example/cover.jpg", pg
with mock.patch("app.chat.linkpreview.requests.get", side_effect=fake_get), mock.patch.object(_lp, "_public_host", return_value=True), \
     mock.patch.object(_scan, "check_image", side_effect=lambda d: _scan.ScanResult(allowed=False, reasons=["nudity:x"])):
    bad = _lp.preview("https://adult.example/x")
    assert not bad.get("image"), bad                         # a nude picture is never shown
assert mongo.db().link_previews.find_one({"url": "https://ncert.example/book"})   # cached

with mock.patch("app.chat.auth.requests.post", side_effect=fake_post), mock.patch("app.chat.push.send_to_users"):
    c = app.test_client()
    T = lambda u: {"Authorization": "Bearer "+tok(u), "X-Chat-Device": "tphone-123", "X-Chat-Client": "1"}
    _verify.needs = lambda user, device: None
    # link preview over the API
    with mock.patch.object(_lp, "build", return_value={"title": "T", "image": "", "video": False}):
        assert c.get("/api/chat/link-preview?url=https://new.example/a", headers=T("stu1")).get_json()["title"] == "T"
    # teacher photo: students can't, teachers can; a failing photo is refused
    assert c.post("/api/chat/me/photo/upload", headers=T("stu1"), json={"size": 1000}).status_code == 403
    with mock.patch.object(_media, "enabled", return_value=True), mock.patch.object(_media, "upload_link", return_value="https://r2/up"), \
         mock.patch.object(_media, "read", return_value=b"jpg"), mock.patch.object(_media, "delete") as deleted, \
         mock.patch.object(_media, "download_link", return_value="https://r2/get/photo"):
        up = c.post("/api/chat/me/photo/upload", headers=T("teacher1"), json={"size": 20000}).get_json()
        assert up["key"].startswith("a/teacher1/")
        with mock.patch.object(_scan, "check_image", return_value=_scan.ScanResult(allowed=False, reasons=["nudity:x"])):
            assert c.post("/api/chat/me/photo", headers=T("teacher1"), json={"key": up["key"]}).status_code == 422
        up = c.post("/api/chat/me/photo/upload", headers=T("teacher1"), json={"size": 20000}).get_json()
        with mock.patch.object(_scan, "check_image", return_value=_scan.ScanResult(allowed=True)):
            r = c.post("/api/chat/me/photo", headers=T("teacher1"), json={"key": up["key"]}).get_json()
        assert r["avatar"].startswith("https://") and "/api/chat/avatar/teacher1/" in r["avatar"], r
        assert c.post("/api/chat/me/photo", headers=T("teacher2"), json={"key": up["key"]}).status_code == 400   # not theirs
        img = c.get(r["avatar"].split("localhost", 1)[-1])
        assert img.status_code == 302 and img.headers["Location"] == "https://r2/get/photo"
        # shows on their messages and in member lists
        gph = c.post("/api/chat/admin/groups", headers=T("teacher1"), json={"title":"Photo","type":"chat","batch":"none-ph"}).get_json()
        msg = c.post(f"/api/chat/groups/{gph['id']}/messages", headers=T("teacher1"), json={"clientId":"ph-1","text":"hello"}).get_json()["message"]
        assert msg["sender"]["avatar"] == r["avatar"], msg["sender"]
        assert c.delete("/api/chat/me/photo", headers=T("teacher1")).get_json()["avatar"] == "teacher"
    # Sir / Ma'am on teachers' names
    assert c.post("/api/chat/me/honorific", headers=T("stu1"), json={"honorific": "sir"}).status_code == 403
    assert c.post("/api/chat/me/honorific", headers=T("teacher1"), json={"honorific": "sir"}).get_json()["honorific"] == "sir"
    assert c.get("/api/chat/me", headers=T("teacher1")).get_json()["honorific"] == "sir"
    msg = c.post(f"/api/chat/groups/{gph['id']}/messages", headers=T("teacher1"), json={"clientId":"ph-2","text":"class at 5"}).get_json()["message"]
    assert msg["sender"]["name"] == "Anshul Sir", msg["sender"]          # already ends in Sir: not doubled
    assert _svc.with_honorific("Neha", "maam") == "Neha Ma'am" and _svc.with_honorific("Neha Mam", "maam") == "Neha Mam"
    assert _svc.with_honorific("Rahul", "sir") == "Rahul Sir" and _svc.with_honorific("Rahul", "") == "Rahul"
    # a student without a name is asked for one; once saved it is used everywhere
    USERS["stu9"] = {"_id": "stu9", "name": "", "role": "student", "reference": "pace", "coachingBatch": []}
    me9 = c.get("/api/chat/me", headers=T("stu9")).get_json()
    assert me9["needsName"] is True, me9
    assert c.post("/api/chat/me/name", headers=T("stu9"), json={"name": "x"}).status_code == 400
    assert c.post("/api/chat/me/name", headers=T("stu9"), json={"name": "  Priya   Verma "}).get_json()["name"] == "Priya Verma"
    assert c.get("/api/chat/me", headers=T("stu9")).get_json()["needsName"] is False
    assert mongo.db().users.find_one({"_id": "stu9"})["name"] == "Priya Verma"
    assert c.get("/api/chat/me", headers=T("stu1")).get_json()["needsName"] is False
print("PREVIEW / PHOTO / SIR / NAME TESTS PASSED")
