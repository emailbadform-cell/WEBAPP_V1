from kalshi_market_stream import KalshiMarketStream

def test_subscription_order_does_not_reconnect_generation():
    s=KalshiMarketStream('x',lambda:{})
    s.set_markets(['CUR','NEXT','EXPECTED']); g=s.generation
    s.books={'CUR':{'sid':1},'OLD':{'sid':2}}; s.tickers={'OLD':{}}; s.trades={'OLD':{}}; s.sid_seq={1:10,2:20}
    s.set_markets(['EXPECTED','CUR','NEXT'])
    assert s.generation==g
    assert 'OLD' not in s.books and 'OLD' not in s.tickers and 'OLD' not in s.trades
    assert 2 not in s.sid_seq

def test_source_contains_kalshi_only_display_and_safe_json():
    a=open('app.py',encoding='utf-8').read(); h=open('static/index.html',encoding='utf-8').read()
    assert 'FINAL_TARGET_KALSHI_PRIMARY_V2' in a
    assert 'LOCAL_BRTI_60S_FALLBACK' not in a
    assert 'KALSHI FINAL TARGET' in h
    assert 'fetchJsonSafe' in h
    assert '/api/runtime/health' in a
