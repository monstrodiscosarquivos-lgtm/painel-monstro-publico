"""Parser isolado. Não ligado aos pedidos: a API real não traz URLs de origem."""
from urllib.parse import urlsplit, parse_qs
import re
import unicodedata


def extrair(url='', referrer=''):
    qs=parse_qs(urlsplit(url).query)
    def seguro(chave):
        # Vocabulário de campanha: rejeita email, URL, espaços, tokens e valores longos.
        v=(qs.get(chave) or [''])[0]
        if len(v)>100 or not re.fullmatch(r'[\w.\- ]*',v) or re.search(r'@|token|bearer|[a-f0-9]{32,}',v,re.I): return ''
        return v
    d={k:seguro(k) for k in ['utm_source','utm_medium','utm_campaign','utm_content']}
    source,medium=d['utm_source'].lower(),d['utm_medium'].lower()
    host=urlsplit(referrer).hostname or ''
    origem='direto/organico'
    if medium=='email' or source=='brevo': origem='email'
    elif 'fbclid' in qs or source in ('facebook','instagram') and medium in ('paid','cpc'): origem='meta_ads'
    elif source=='instagram' or host.endswith('instagram.com'): origem='instagram_organico'
    elif 'gclid' in qs or source=='google' or host.endswith('google.com'): origem='google'
    elif source=='whatsapp' or host in ('wa.me','whatsapp.com'): origem='whatsapp'
    return {**d,'origem':origem}
