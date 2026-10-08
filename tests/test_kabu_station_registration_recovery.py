import pytest
from app.market.kabu_station_registration_plan import build_registration_codes
from app.market.kabu_station_realtime_service import KabuStationRealtimeService

class Provider:
    def __init__(self, fail=None):
        self.codes = ('7093', '4980', '9551', '7120', '9552')
        self.events = []
        self.fail = fail
    def connect(self):
        self.events.append('connect')
        if self.fail == 'connect': raise RuntimeError('auth failed')
    def unregister_all(self):
        self.events.append('clear')
        if self.fail == 'clear': raise RuntimeError('clear failed')
        self.codes = ()
    def register_codes(self, codes):
        self.events.append('register')
        if self.fail == 'register': raise RuntimeError('register failed')
        result = tuple(dict.fromkeys((*self.codes, *codes)))
        if len(result) > 50: raise RuntimeError('4002006')
        self.codes = result
        return tuple(codes)

class Socket:
    def __init__(self, **kwargs): self.started = False
    def start(self): self.started = True
    def stop(self): pass

def make(fail=None):
    provider = Provider(fail)
    return provider, KabuStationRealtimeService(provider=provider, websocket_client_factory=Socket)

def test_restart_replaces_stale_five_with_fifty():
    provider, service = make()
    codes = tuple(str(1000+i) for i in range(48)) + ('7093', '4980')
    assert service.start(codes) == codes
    assert provider.codes == codes
    assert provider.events == ['connect', 'clear', 'register']
    assert service._websocket_client.started

@pytest.mark.parametrize('codes', [[], ['bad'], [str(1000+i) for i in range(51)]])
def test_invalid_start_does_not_mutate_api(codes):
    provider, service = make()
    with pytest.raises(ValueError): service.start(codes)
    assert provider.events == []
    assert len(provider.codes) == 5

@pytest.mark.parametrize('failure,events', [('connect',['connect']), ('clear',['connect','clear']), ('register',['connect','clear','register'])])
def test_failure_never_starts_socket(failure, events):
    provider, service = make(failure)
    with pytest.raises(RuntimeError): service.start(['7203'])
    assert provider.events == events
    assert service._websocket_client is None
    assert service.registered_codes == ()

def test_duplicate_start_does_not_clear_active_subscription():
    provider, service = make()
    service.start(['7203']); provider.events.clear()
    with pytest.raises(RuntimeError): service.start(['9984'])
    assert provider.events == []
    assert service.registered_codes == ('7203',)

def test_invalid_update_preserves_registration():
    provider, service = make()
    service.start(['7203']); provider.events.clear()
    with pytest.raises(ValueError): service.update_registered_codes(['bad'])
    assert provider.events == []
    assert service.registered_codes == ('7203',)

def test_update_clears_old_codes():
    provider, service = make()
    service.start(['7203'])
    assert service.update_registered_codes(['9984']) == ('9984',)
    assert provider.codes == ('9984',)

def test_positions_have_priority_over_full_watchlist():
    watchlist = tuple(str(1000+i) for i in range(50))
    result = build_registration_codes(watchlist, ['9551','9551','7120'])
    assert result == ('9551','7120',*watchlist[:48])

def test_overlapping_positions_do_not_waste_slots():
    assert build_registration_codes(['7203','9984'],['9984']) == ('9984','7203')

def test_too_many_positions_fail_instead_of_silent_truncation():
    with pytest.raises(ValueError):
        build_registration_codes([], (str(1000+i) for i in range(51)))

@pytest.mark.parametrize('limit',[0,51])
def test_invalid_registration_limit(limit):
    with pytest.raises(ValueError): build_registration_codes(['7203'], [], maximum_symbols=limit)
