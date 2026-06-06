from fastapi.testclient import TestClient
from main import app
from database import engine, Base, get_db
import models
from auth import get_password_hash
from sqlalchemy.orm import Session

Base.metadata.create_all(bind=engine)

with Session(bind=engine) as db:
    user = db.query(models.User).filter(models.User.email == 'debug@example.com').first()
    if not user:
        org = models.Organization(name='Debug Org')
        db.add(org)
        db.commit()
        db.refresh(org)
        user = models.User(
            email='debug@example.com',
            password_hash=get_password_hash('secret123'),
            role='Viewer',
            organization_id=org.id,
            email_verified=True
        )
        db.add(user)
        db.commit()

client = TestClient(app)
response = client.post('/api/v1/auth/login', json={'email': 'debug@example.com', 'password': 'secret123'})
print('status', response.status_code)
print('headers', response.headers)
print('body', response.text)
if response.status_code >= 400:
    print('json?', response.headers.get('content-type'))
    try:
        print('json body:', response.json())
    except Exception as e:
        print('json parse error:', e)
