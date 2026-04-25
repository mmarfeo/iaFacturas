from starlette.testclient import TestClient
from app.main import app as application

with TestClient(application, raise_server_exceptions=False) as client:
    r = client.get('/app/perfil/api-key')
    print('STATUS:', r.status_code)
    print('BODY:', r.text[:1000])
