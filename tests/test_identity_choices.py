import pytest
from app.qloo import QlooClient, Entity, normalize_name
from app.receipt import AuditError, audit


@pytest.mark.parametrize('left,right', [('Guard & Grace','Guard and Grace'), ('Work & Class','Work and Class'),
                                       ('The Denver Central Market','Denver Central Market')])
def test_informal_aliases_resolve_to_the_same_city_verified_identity(monkeypatch, left, right):
    client = QlooClient('placeholder')
    monkeypatch.setattr(client, '_get', lambda *a: {'results':[{'entity_id':'place', 'name':right,
       'types':['urn:entity:place'], 'properties':{'geocode':{'city':'Denver'}}}]})
    assert normalize_name(left) == normalize_name(right)
    assert client.resolve_place(left, 'Denver').entity_id == 'place'


def test_alias_collision_is_still_ambiguous_and_unknown_ids_are_rejected(monkeypatch):
    client = QlooClient('placeholder')
    monkeypatch.setattr(client, '_get', lambda *a: {'results':[
       {'entity_id':'old', 'name':'Dune', 'types':['urn:entity:movie'], 'properties':{'release_date':'1984-12-14'}},
       {'entity_id':'new', 'name':'Dune', 'types':['urn:entity:movie'], 'properties':{'release_date':'2021-10-22'}}]})
    assert client.resolve_anchor('Dune') is None
    assert [item.release_year for item in client.anchor_options('Dune')] == ['1984','2021']
    assert client.resolve_anchor('Dune', 'new').release_year == '2021'
    assert client.resolve_anchor('Dune', 'unrelated') is None


def test_revisions_cannot_switch_the_selected_title_or_drop_the_selection():
    result = audit(anchors=['Dune','Kendrick Lamar'], candidates=['Harbor Street Grill'],
                   city='Denver', force_demo=True, anchor_selections={'Dune':'demo-anchor-dune'})
    for selections in ({}, {'Dune':'another-title'}):
        with pytest.raises(AuditError, match='selected title identities'):
            audit(anchors=['Dune','Kendrick Lamar'], candidates=['Juniper House'], city='Denver',
                  force_demo=True, revision_of=result['audit_id'], anchor_selections=selections)
    revised = audit(anchors=['Dune','Kendrick Lamar'], candidates=['Juniper House'], city='Denver',
                    force_demo=True, revision_of=result['audit_id'], anchor_selections={'Dune':'demo-anchor-dune'})
    assert revised['comparison_fingerprint'] == result['comparison_fingerprint']


def test_repeat_controls_cannot_switch_between_different_titles_with_the_same_name():
    from app.main import BatchTestRequest
    from pydantic import ValidationError
    from datetime import datetime, timezone
    profiles = [{'profile_id':str(i), 'control_group':'same', 'anchors':['Dune','Kendrick Lamar'],
                 'anchor_selections':{'Dune':entity_id}, 'recommendations':['Guard and Grace']}
                for i,entity_id in enumerate(['film-1984','film-2021'])]
    with pytest.raises(ValidationError, match='same tastes'):
        BatchTestRequest(agent_name='agent',agent_version='1',prompt_version='1',
                         captured_at=datetime.now(timezone.utc),city='Denver',profiles=profiles)
