from layan_engine.browser.challenge import ChallengeType, detect_challenge


class _FakePage:
    def __init__(self, url: str, text: str):
        self.url = url
        self._text = text

    async def evaluate(self, _script):
        return self._text


async def test_dashboard_with_noisy_words_in_code_is_not_a_challenge():
    page = _FakePage(
        "https://studio.youtube.com/channel/UCabc/analytics/tab-overview",
        "Channel analytics\nViews 12.3K\nWatch time (hours) 410\nSubscribers +52",
    )
    assert not (await detect_challenge(page)).detected


async def test_visible_two_factor_prompt_is_detected():
    page = _FakePage("https://accounts.google.com/v3/signin", "2-Step Verification\nEnter the 6-digit code")
    r = await detect_challenge(page)
    assert r.detected and r.challenge_type == ChallengeType.TWO_FACTOR


async def test_facebook_checkpoint_url_is_detected():
    page = _FakePage("https://www.facebook.com/checkpoint/1501092823525282/", "")
    r = await detect_challenge(page)
    assert r.detected and r.challenge_type == ChallengeType.SECURITY_CHECKPOINT


async def test_hex_id_containing_2fa_is_not_two_factor():
    page = _FakePage("https://business.facebook.com/latest/insights?asset_id=9a2fa31", "Insights\nReach 1,204")
    assert not (await detect_challenge(page)).detected
