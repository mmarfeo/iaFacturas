from starlette.testclient import TestClient
from app.main import app as application
from app.core.security import create_access_token

# Genera un token para el usuario ID 1 (primer usuario registrado)
token = create_access_token(1)

with TestClient(application, raise_server_exceptions=False, follow_redirects=False) as client:
    # Sin cookie — debe devolver 302
    r1 = client.get('/app/perfil/api-key')
    print('SIN AUTH  status:', r1.status_code, '(esperado: 302)')

    # Con cookie de usuario ID 1
    r2 = client.get('/app/perfil/api-key', cookies={'access_token': token})
    print('CON AUTH  status:', r2.status_code)
    if r2.status_code >= 400:
        print('ERROR BODY:', r2.text[:2000])
    elif r2.status_code == 200:
        print('OK — primeros 300 chars:', r2.text[:300])
