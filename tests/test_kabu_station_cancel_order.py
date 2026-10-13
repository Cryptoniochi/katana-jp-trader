from app.market.kabu_station_client import KabuStationClient,KabuStationClientSettings
def make(response=b'{"Result":0,"OrderId":"OID"}'):
    calls=[]
    def transport(method,url,headers,body,timeout):
        calls.append((method,url,body))
        if url.endswith("/token"): return 200,b'{"ResultCode":0,"Token":"t"}'
        return 200,response
    return KabuStationClient(settings=KabuStationClientSettings(api_password="p"),transport=transport),calls
def test_cancel_order_put_once():
    c,calls=make(); assert c.cancel_order("OID")["Result"]==0
    x=[v for v in calls if v[1].endswith("/cancelorder")]
    assert len(x)==1 and x[0][0]=="PUT" and b'"OrderId": "OID"' in x[0][2]
def test_cancel_mismatched_id_fails_closed():
    c,_=make(b'{"Result":0,"OrderId":"OTHER"}')
    try:c.cancel_order("OID")
    except Exception:return
    raise AssertionError("must fail")
