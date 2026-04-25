import asyncio
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.usuario import Usuario
from starlette.testclient import TestClient
from app.main import app as application


async def get_first_user_id():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Usuario).limit(1))
        user = res.scalar_one_or_none()
        if user:
            print(f'Usuario encontrado: id={user.id} email={user.email} active={user.is_active}')
            return user.id
        print('NO HAY USUARIOS en la DB')
        return None


user_id = asyncio.run(get_first_user_id())

if user_id:
    token = create_access_token(user_id)
    with TestClient(application, raise_server_exceptions=False, follow_redirects=False) as client:
        r = client.get('/app/perfil/api-key', cookies={'access_token': token})
        print('CON AUTH  status:', r.status_code)
        if r.status_code >= 400:
            print('ERROR BODY:', r.text[:2000])
        elif r.status_code == 200:
            print('OK — primeros 300 chars:', r.text[:300])
        else:
            print('REDIRECT a:', r.headers.get('location'))
