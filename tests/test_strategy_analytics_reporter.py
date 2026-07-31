from datetime import datetime,timezone
import json
from app.runtime.strategy_analytics_models import StrategyAnalyticsReport,StrategyPerformance
from app.runtime.strategy_analytics_reporter import StrategyAnalyticsReporter
NOW=datetime(2026,8,3,tzinfo=timezone.utc)

def test_write_reports(tmp_path):
    p=StrategyPerformance('orb',2,2,1,1,0,0,1000,0,1000,1000,None,1.0,float('inf'),30,0)
    r=StrategyAnalyticsReport(NOW,'/tmp/katana.db',(p,),())
    jp,cp,hp=StrategyAnalyticsReporter(tmp_path).write(r)
    assert jp.exists() and cp.exists() and hp.exists()
    assert json.loads(jp.read_text(encoding='utf-8'))['performances'][0]['profit_factor']=='Infinity'
    assert 'orb' in cp.read_text(encoding='utf-8-sig')
    assert 'Project KATANA' in hp.read_text(encoding='utf-8')
