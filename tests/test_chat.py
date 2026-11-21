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
         "teacher1": {"_id":"teacher1","name":"Anshul Sir","role":"teacher","reference":"pace","coachingBatch":[]}}
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
    c.post(f"/api/chat/admin/groups/{grp['id']}/members", headers=H("teacher1"), json={"members":[{"userId":"stu1","rollNo":"23"}]})
    for x in (s1,s2,t1): x.get_received("/chat")
    # student sends a message
    ack = s1.emit("send", {"groupId": grp["id"], "clientId":"c-1", "text":"Sir, doubt in Q5?"}, namespace="/chat", callback=True)
    assert ack["ok"] and ack["message"]["seq"]==1 and ack["message"]["sender"]["label"]=="Roll 23", ack
    got = [e for e in s2.get_received("/chat") if e["name"]=="message"]
    assert got and (got[0]["args"][0] if isinstance(got[0]["args"],list) else got[0]["args"])["text"]=="Sir, doubt in Q5?"
    # resend same clientId -> same message, no duplicate
    ack2 = s1.emit("send", {"groupId": grp["id"], "clientId":"c-1", "text":"Sir, doubt in Q5?"}, namespace="/chat", callback=True)
    assert ack2["message"]["seq"]==1 and mongo.db().messages.count_documents({})==1
    # student can't post in announcements; teacher can
    a3 = s1.emit("send", {"groupId": ann["id"], "clientId":"c-2", "text":"hi"}, namespace="/chat", callback=True)
    assert not a3["ok"] and a3["error"]=="read_only"
    a4 = t1.emit("send", {"groupId": ann["id"], "clientId":"t-1", "text":"Test on Sunday 9 AM"}, namespace="/chat", callback=True)
    assert a4["ok"] and a4["message"]["sender"]["label"]=="Teacher"
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
    assert [m["seq"] for m in h["messages"]]==[1,2], h
    h2 = c.get(f"/api/chat/groups/{grp['id']}/messages?after=1", headers=H("stu2")).get_json()
    assert [m["seq"] for m in h2["messages"]]==[2]
    # unread + read receipts
    gl2 = {g["id"]:g for g in c.get("/api/chat/groups", headers=H("stu2")).get_json()["groups"]}
    assert gl2[grp["id"]]["unread"]==2 and gl2[ann["id"]]["unread"]==1
    s2.emit("read", {"groupId": grp["id"], "seq": 2}, namespace="/chat", callback=True)
    gl3 = {g["id"]:g for g in c.get("/api/chat/groups", headers=H("stu2")).get_json()["groups"]}
    assert gl3[grp["id"]]["unread"]==0
    # typing reaches others not sender
    for x in (s1,s2,t1): x.get_received("/chat")
    s1.emit("typing", {"groupId": grp["id"], "typing": True}, namespace="/chat", callback=True)
    assert any(e["name"]=="typing" for e in s2.get_received("/chat"))
    assert not any(e["name"]=="typing" for e in s1.get_received("/chat"))
    # delete own message; others get message_deleted
    d = c.delete(f"/api/chat/groups/{grp['id']}/messages/1", headers=H("stu1")).get_json()
    assert d["ok"]; assert any(e["name"]=="message_deleted" for e in s2.get_received("/chat"))
    assert c.delete(f"/api/chat/groups/{grp['id']}/messages/2", headers=H("stu2")).status_code==403
    # non-member can't read; removed member is dropped
    c.delete(f"/api/chat/admin/groups/{grp['id']}/members/stu2", headers=H("teacher1"))
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
    upd = c.patch(f"/api/chat/admin/groups/{grp['id']}", headers=H("teacher1"), json={"autoJoin": False}).get_json()
    assert upd["id"] == grp["id"] and mongo.db().groups.find_one({"_id": grp["id"]})["autoJoin"] is None
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
    print("ALL CHAT TESTS PASSED")
