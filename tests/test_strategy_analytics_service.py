import sqlite3
from datetime import datetime,timedelta,timezone
import pytest
from app.database import initialize_database
from app.runtime.strategy_analytics_service import StrategyAnalyticsService
NOW=datetime(2026,8,3,tzinfo=timezone.utc)

def setup_round_trip(db,strategy,prefix,entry,exit_):
    with sqlite3.connect(db) as c:
        for action,side,price,at,suffix in [('buy','buy',entry,NOW,'b'),('exit','sell',exit_,NOW+timedelta(minutes=30),'x')]:
            sid=f'{prefix}-{suffix}-s'; oid=f'{prefix}-{suffix}-o'; eid=f'{prefix}-{suffix}-e'
            c.execute("INSERT INTO trade_signals(signal_id,code,strategy_name,action,generated_at,signal_price,quantity,reason,metadata_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,100,'test','{}','processed',?,?)",(sid,'7203',strategy,action,at.isoformat(),price,at.isoformat(),at.isoformat()))
            c.execute("INSERT INTO trade_orders(order_id,signal_id,code,side,order_type,quantity,status,filled_quantity,created_at,updated_at) VALUES(?,?,?,?, 'market',100,'filled',100,?,?)",(oid,sid,'7203',side,at.isoformat(),at.isoformat()))
            c.execute("INSERT INTO trade_executions(execution_id,signal_id,order_id,broker_order_id,code,side,quantity,execution_price,executed_at,broker_name,commission,slippage,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,100,?,?,'paper',100,0,'{}',?,?)",(eid,sid,oid,'broker-'+oid,'7203',side,price,at.isoformat(),at.isoformat(),at.isoformat()))
        c.commit()

def test_analyze_by_strategy(tmp_path):
    db=tmp_path/'katana.db'; initialize_database(db)
    setup_round_trip(db,'orb','orb',1000,1020)
    setup_round_trip(db,'pullback','pb',1000,990)
    report=StrategyAnalyticsService(db,now_provider=lambda:NOW).analyze()
    m={x.strategy_name:x for x in report.performances}
    assert m['orb'].completed_trade_count==1
    assert m['orb'].net_profit_loss==pytest.approx(1800)
    assert m['orb'].profit_factor==float('inf')
    assert m['pullback'].loss_count==1
    assert m['pullback'].maximum_drawdown==pytest.approx(1200)

def test_open_entry_not_counted_as_closed(tmp_path):
    db=tmp_path/'katana.db'; initialize_database(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO trade_signals(signal_id,code,strategy_name,action,generated_at,signal_price,quantity,reason,metadata_json,status,created_at,updated_at) VALUES('s','7203','orb','buy',?,1000,100,'test','{}','processed',?,?)",(NOW.isoformat(),NOW.isoformat(),NOW.isoformat()))
        c.execute("INSERT INTO trade_orders(order_id,signal_id,code,side,order_type,quantity,status,filled_quantity,created_at,updated_at) VALUES('o','s','7203','buy','market',100,'filled',100,?,?)",(NOW.isoformat(),NOW.isoformat()))
        c.execute("INSERT INTO trade_executions(execution_id,signal_id,order_id,broker_order_id,code,side,quantity,execution_price,executed_at,broker_name,commission,slippage,metadata_json,created_at,updated_at) VALUES('e','s','o','bo','7203','buy',100,1000,?,'paper',0,0,'{}',?,?)",(NOW.isoformat(),NOW.isoformat(),NOW.isoformat()))
        c.commit()
    r=StrategyAnalyticsService(db,now_provider=lambda:NOW).analyze()
    assert r.performances[0].execution_count==1
    assert r.performances[0].completed_trade_count==0
