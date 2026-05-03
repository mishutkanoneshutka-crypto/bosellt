from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from database.base import SessionLocal, setup_database
from config import load_config
from database.models import Product, SupportTicket

app = FastAPI(title='Shop Admin Reserve')
config = load_config()


def is_authenticated(request: Request) -> bool:
    return request.cookies.get('wa_user') == config.web_admin_username


@app.on_event('startup')
async def startup() -> None:
    setup_database(config.database_url)


@app.get('/login', response_class=HTMLResponse)
async def login_page() -> str:
    return """
    <html><body>
    <h2>Web Admin Login</h2>
    <form method='post' action='/login'>
      <input name='username' placeholder='Username'/><br/><br/>
      <input name='password' placeholder='Password' type='password'/><br/><br/>
      <button type='submit'>Login</button>
    </form>
    </body></html>
    """


@app.post('/login')
async def login(username: str = Form(...), password: str = Form(...)):
    if username != config.web_admin_username or password != config.web_admin_password:
        return HTMLResponse('<h3>Invalid credentials</h3><a href="/login">Back</a>', status_code=401)
    response = RedirectResponse(url='/', status_code=302)
    response.set_cookie('wa_user', username, httponly=True)
    return response


@app.get('/logout')
async def logout():
    response = RedirectResponse(url='/login', status_code=302)
    response.delete_cookie('wa_user')
    return response


@app.get('/', response_class=HTMLResponse)
async def index(request: Request) -> str | RedirectResponse:
    if not is_authenticated(request):
        return RedirectResponse('/login', status_code=302)
    async with SessionLocal() as session:
        products_result = await session.execute(select(Product).order_by(Product.id.desc()))
        tickets_result = await session.execute(select(SupportTicket).order_by(SupportTicket.id.desc()))
        products = list(products_result.scalars().all())
        tickets = list(tickets_result.scalars().all())

    rows = ''.join(
        f"<tr><td>{p.id}</td><td>{p.title}</td><td>{p.price}</td><td>{p.discount_percent}%</td><td>{'yes' if p.is_active else 'no'}</td><td><a href='/product/{p.id}'>edit</a></td></tr>"
        for p in products
    )
    ticket_rows = ''.join(
        f"<tr><td>{t.id}</td><td>{t.user_id}</td><td>{t.status}</td><td>{t.message_text}</td><td>{t.admin_reply or ''}</td></tr>"
        for t in tickets[:50]
    )
    return f"""
    <html>
      <head><title>Reserve Admin</title></head>
      <body>
        <h1>Reserve Admin Panel</h1>
        <p><a href='/logout'>Logout</a></p>
        <h2>Products</h2>
        <table border='1' cellpadding='6'>
          <tr><th>ID</th><th>Title</th><th>Price</th><th>Discount</th><th>Active</th><th>Action</th></tr>
          {rows}
        </table>
        <h2>Tickets</h2>
        <table border='1' cellpadding='6'>
          <tr><th>ID</th><th>User</th><th>Status</th><th>Message</th><th>Reply</th></tr>
          {ticket_rows}
        </table>
      </body>
    </html>
    """


@app.get('/product/{product_id}', response_class=HTMLResponse)
async def edit_product_page(product_id: int, request: Request):
    if not is_authenticated(request):
        return RedirectResponse('/login', status_code=302)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
    if not product:
        return HTMLResponse('Product not found', status_code=404)
    checked = 'checked' if product.is_active else ''
    return f"""
    <html><body>
    <h2>Edit product #{product.id}</h2>
    <form method='post' action='/product/{product.id}'>
      <input name='title' value='{product.title}' placeholder='Title'/><br/><br/>
      <textarea name='description' placeholder='Description'>{product.description}</textarea><br/><br/>
      <input name='price' value='{product.price}' placeholder='Price'/><br/><br/>
      <input name='discount_percent' value='{product.discount_percent}' placeholder='Discount percent'/><br/><br/>
      <label><input type='checkbox' name='is_active' {checked}/> Active</label><br/><br/>
      <button type='submit'>Save</button>
    </form>
    <p><a href='/'>Back</a></p>
    </body></html>
    """


@app.post('/product/{product_id}')
async def edit_product_submit(product_id: int, request: Request, title: str = Form(...), description: str = Form(...), price: str = Form(...), discount_percent: int = Form(...), is_active: str | None = Form(None)):
    if not is_authenticated(request):
        return RedirectResponse('/login', status_code=302)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if not product:
            return HTMLResponse('Product not found', status_code=404)
        product.title = title
        product.description = description
        product.price = price
        product.discount_percent = discount_percent
        product.is_active = is_active is not None
        await session.commit()
    return RedirectResponse(url='/', status_code=302)
