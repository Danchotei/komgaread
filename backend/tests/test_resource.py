from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.mark.parametrize('failure', ['client', 'detail', 'domain', 'cover', None])
def test_resource_lookup_failures(monkeypatch, failure):
    def fail():
        raise RuntimeError('upstream unavailable')

    def detail(jmid):
        if failure == 'detail':
            fail()
        return SimpleNamespace(title='Example', author=['Author'], tags=['Tag'])

    def cover(jmid, path):
        downloaded.append(main.Path(path))
        main.Path(path).write_bytes(b'cover')
        if failure == 'cover':
            fail()

    def client():
        if failure == 'client':
            fail()
        return SimpleNamespace(get_album_detail=detail, download_album_cover=cover)

    def domain():
        if failure == 'domain':
            fail()
        return 'jm.example'

    downloaded = []
    # 封面下载使用模拟数据，不访问网络或真实持久化数据。
    monkeypatch.setattr(main.JmOption, 'default', lambda: SimpleNamespace(new_jm_client=client))
    monkeypatch.setattr(main.JmModuleConfig, 'get_html_domain', domain)
    main.sessions.update({'reader': ('token', main.time() + 60)})
    browser = TestClient(main.app)
    browser.cookies.set(main.COOKIE_NAME, 'reader')
    response = browser.post('/api/resource/lookup', json={'jmid': '123'}, headers={'Origin': 'http://127.0.0.1:5173'})
    if failure in {'client', 'detail', 'domain'}:
        assert response.status_code == 502
        assert response.json()['detail'] == '获取漫画信息失败，请稍后重试'
    else:
        assert response.status_code == 200
        data = response.json()
        assert data['title'] == 'Example'
        assert data['link'] == 'https://jm.example/album/123'
        assert data['cover_url'] == (None if failure == 'cover' else 'data:image/png;base64,Y292ZXI=')
    assert all(not path.parent.exists() for path in downloaded)


def test_resource_lookup_requires_login():
    response = TestClient(main.app).post('/api/resource/lookup', json={'jmid': '123'}, headers={'Origin': 'http://127.0.0.1:5173'})
    assert response.status_code == 401
