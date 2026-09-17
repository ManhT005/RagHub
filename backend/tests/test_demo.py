import os
import tempfile
from uuid import uuid4
os.environ["RAGHUB_DATA"] = tempfile.mkdtemp(prefix="raghub-tests-")
from fastapi.testclient import TestClient
from app.main import app, buckets
client = TestClient(app)

def account():
    email = f"{uuid4()}@test.local"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "demo-password"})
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["access_token"]}

def setup():
    auth = account()
    wid = client.post("/api/v1/workspaces", headers=auth, json={"name": "Admissions"}).json()["id"]
    bid = client.post(f"/api/v1/workspaces/{wid}/chatbots", headers=auth, json={"name": "Assistant"}).json()["id"]
    return auth, wid, bid

def upload(auth, wid, name="guide.txt", data=b"Tuition costs 18 million per semester.", mime="text/plain"):
    return client.post(f"/api/v1/workspaces/{wid}/documents", headers=auth, files={"file": (name, data, mime)})

def test_document_chat_reindex_delete():
    auth, wid, bid = setup()
    response = upload(auth, wid)
    assert response.status_code == 202
    did = response.json()["id"]
    docs = client.get(f"/api/v1/workspaces/{wid}/documents", headers=auth).json()
    assert docs[0]["status"] == "READY"
    response = client.post(f"/api/v1/chatbots/{bid}/test", headers=auth, json={"message": "Tuition"})
    assert response.status_code == 200
    assert "18 million" in response.text and "event: citations" in response.text and "event: done" in response.text
    assert upload(auth, wid).status_code == 409
    assert client.post(f"/api/v1/documents/{did}/reindex", headers=auth).status_code == 202
    assert client.delete(f"/api/v1/documents/{did}", headers=auth).status_code == 204
    response = client.post(f"/api/v1/chatbots/{bid}/test", headers=auth, json={"message": "Tuition"})
    assert "18 million" not in response.text

def test_account_and_workspace_isolation():
    auth, wid, bid = setup()
    did = upload(auth, wid).json()["id"]
    other = account()
    for path in [f"/workspaces/{wid}/documents", f"/workspaces/{wid}/chatbots"]:
        assert client.get('/api/v1'+path, headers=other).status_code == 404
    assert client.delete(f"/api/v1/documents/{did}", headers=other).status_code == 404
    assert client.post(f"/api/v1/chatbots/{bid}/test", headers=other, json={"message":"Tuition"}).status_code == 404
    wid2 = client.post('/api/v1/workspaces', headers=auth, json={"name":"Empty"}).json()["id"]
    bid2 = client.post(f'/api/v1/workspaces/{wid2}/chatbots', headers=auth, json={"name":"Other"}).json()["id"]
    r = client.post(f'/api/v1/chatbots/{bid2}/test', headers=auth, json={"message":"Tuition"})
    assert "18 million" not in r.text

def test_public_origins_publish_and_rate_limit():
    auth, wid, bid = setup()
    path=f'/api/v1/public/chatbots/{bid}/chat'
    body={"message":"Tuition"}
    origin={"Origin":"http://localhost:8081"}
    assert client.post(path,headers=origin,json=body).status_code == 404
    client.post(f'/api/v1/chatbots/{bid}/publish',headers=auth)
    assert client.post(path,json=body).status_code == 403
    assert client.post(path,headers={"Origin":"https://evil.example"},json=body).status_code == 403
    for _ in range(20):
        assert client.post(path,headers=origin,json=body).status_code == 200
    assert client.post(path,headers=origin,json=body).status_code == 429
    client.post(f'/api/v1/chatbots/{bid}/publish',headers=auth)
    assert client.post(path,headers=origin,json=body).status_code == 404

def test_upload_validation_and_failure():
    auth,wid,bid=setup()
    assert upload(auth,wid,'evil.pdf',b'not PDF','application/pdf').status_code == 422
    assert upload(auth,wid,'file.exe',b'code').status_code == 415
    assert upload(auth,wid,'big.txt',b'a'*(5*1024*1024+1)).status_code == 413
    assert upload(auth,wid,'empty.txt',b'').status_code == 422
    assert upload(auth,wid,'invalid.txt',b'\xff').status_code == 202
    docs=client.get(f'/api/v1/workspaces/{wid}/documents',headers=auth).json()
    assert docs[0]['status']=='FAILED'

def test_logout_revokes_token():
    auth=account()
    assert client.get('/api/v1/workspaces').status_code == 401
    assert client.post('/api/v1/auth/logout',headers=auth).status_code == 204
    assert client.get('/api/v1/workspaces',headers=auth).status_code == 401

def test_pdf_text_and_page_citation():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from io import BytesIO
    writer=PdfWriter()
    page=writer.add_blank_page(width=400,height=400)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 200 Td (Scholarship covers half of tuition.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    data=BytesIO();writer.write(data)
    auth,wid,bid=setup()
    assert upload(auth,wid,'scholarship.pdf',data.getvalue(),'application/pdf').status_code == 202
    r=client.post(f'/api/v1/chatbots/{bid}/test',headers=auth,json={"message":"Scholarship"})
    assert 'Scholarship covers' in r.text and '"page": 1' in r.text
