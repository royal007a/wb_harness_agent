"""Render trusted static pages under the local or fixed nginx mount point."""
import re

from fastapi.responses import HTMLResponse

from .service import ROOT


def frontend_page(request, filename):
    # local_boundary validates this header; nginx overwrites it, not appends.
    prefix = request.headers.get('x-forwarded-prefix', '')
    html = (ROOT / 'frontend' / filename).read_text(encoding='utf-8')
    html = html.replace('</head>', '<script src="/static/paths.js"></script></head>')
    # Load the shared helper before the page's deferred scripts execute.
    html = re.sub(r'\b(href|src)="/(?!/)', lambda m: m[1] + '="' + prefix + '/', html)
    return HTMLResponse(html)
