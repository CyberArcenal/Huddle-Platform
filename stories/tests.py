from django.test import TestCase

# Create your tests here.
def test_set_cover_success(client, user, highlight, story):
    # story belongs to user and is in highlight
    resp = client.post(f"/highlights/{highlight.id}/set-cover/", {"cover_story_id": story.id}, auth=user)
    assert resp.status_code == 200
    assert resp.data["cover_url"] is not None  # or check cover id

def test_set_cover_not_owner(client, other_user, highlight, story):
    resp = client.post(f"/highlights/{highlight.id}/set-cover/", {"cover_story_id": story.id}, auth=other_user)
    assert resp.status_code == 403

def test_set_cover_story_not_in_highlight(client, user, highlight, other_story):
    resp = client.post(f"/highlights/{highlight.id}/set-cover/", {"cover_story_id": other_story.id}, auth=user)
    assert resp.status_code == 404
