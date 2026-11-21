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
from app.chat import moderation
moderation.settings.OPENAI_API_KEY = ""          # no network in tests

USERS = {"stu1": {"_id":"stu1","name":"Riya","role":"student","reference":"pace","coachingBatch":["apex"]},
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
