import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from scripts.receipt_mcp import ReceiptClient, create_server


@pytest.mark.parametrize('url', ['http://external.test','https://user:password@external.test',
                                 'https://external.test/path','https://external.test?token=secret'])
def test_bridge_rejects_insecure_or_credential_bearing_origins(url):
    with pytest.raises(ValueError):
        ReceiptClient(url)


def test_bridge_revision_preserves_real_api_session_and_frozen_evidence(monkeypatch):
    bridge = ReceiptClient('http://127.0.0.1:8132')
    with TestClient(app) as browser:
        def request(path, payload=None):
            response = browser.post(path, json=payload) if payload is not None else browser.get(path)
            if response.status_code >= 400:
                raise ValueError(response.json().get('detail'))
            return response.json()
        monkeypatch.setattr(bridge, 'request', request)
        original = bridge.audit({'anchors':['Kendrick Lamar','The Bear'], 'candidates':['Copper Kettle'],
                                 'city':'Denver','demo':True})
        revised = bridge.audit({'revision_of':original['audit_id'], 'candidates':['Juniper House']})
        assert original['comparison_fingerprint'] == revised['comparison_fingerprint']
        assert not original['approval_eligible'] and revised['approval_eligible']
        assert revised['re_audit_of'] == original['audit_id']
        with pytest.raises(ValueError, match='must keep'):
            bridge.audit({'revision_of':revised['audit_id'],'city':'Austin','candidates':['Harbor Street Grill']})
        with pytest.raises(ValueError, match='did not create'):
            bridge.audit({'revision_of':'foreign-audit','candidates':['Harbor Street Grill']})


def test_real_sdk_exposes_typed_venue_schema_and_no_approval_tool():
    server = create_server(ReceiptClient('http://127.0.0.1:8132'))
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {'resolve_tastes','audit_recommendations','revise_recommendations'}
    schema = next(tool for tool in tools if tool.name == 'audit_recommendations').inputSchema
    assert set(schema['$defs']['Venue']['required']) == {'label','latitude','longitude'}
