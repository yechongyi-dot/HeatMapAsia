"""Single source of truth for everything region-specific.

HeatMap-Asia ranks investment videos across three markets — Japan, Korea and
Singapore — from one app. Each market differs in:

  * search keywords (language + local instruments)
  * which platforms exist (Niconico is Japan-only; Korea/Singapore are
    YouTube + curated "official" channels)
  * the curated official / authoritative channel list
  * how a title is recognised as finance-related (native-script substring
    keywords vs. Latin-token acronyms)
  * which script earns the "local language" scoring bonus

The scrapers, scorer and store all stay region-agnostic: they take a ``region``
id (``"jp"`` / ``"kr"`` / ``"sg"``) and read the rest from :data:`REGIONS`.
"""

from __future__ import annotations

# Default region used when a caller omits one (keeps single-region call sites
# working) and as the app's initial selection.
DEFAULT_REGION = "jp"


# ── Shared negative keywords (entertainment / off-topic) ──
#
# Applied in every region. A title containing any of these is rejected before
# the positive finance check, so short finance tokens (ドル, 円, dollar…) can't
# pull in cooking / vlog / music content.
NEGATIVE_KEYWORDS = [
    # Food / cooking
    "grilled", "recipe", "rice paper", "cooking", "food", "street food", "mukbang",
    "料理", "レシピ", "グルメ", "食べ", "おいしい", "먹방", "레시피", "요리",
    # Entertainment / non-financial
    "vlog", "prank", "reaction", "unboxing", "haul",
    "gaming", "gameplay", "minecraft", "fortnite", "roblox",
    "asmr", "sleep", "meditation",
    "makeup", "beauty", "fashion", "outfit",
    "travel", "tour", "sightseeing",
    "music", "song", "cover", "dance", "mv",
    "sports", "football", "soccer", "basketball", "baseball",
    "브이로그", "예능", "드라마", "메이크업", "게임",
    # Idol / variety / story-time / fortune (catch short tokens like ドル/円)
    "アイドル", "スカッと", "修羅場", "占い", "燃え尽き", "バーンアウト",
    # Pets / animals
    "cat ", "dog ", "kitten", "puppy", "ペット", "猫", "犬",
]

# Latin tickers/ratios that collide with common lowercase words: PER↔"per",
# ROE↔"roe", PBR↔"pbr". Matched case-SENSITIVELY (uppercase only). Shared.
LATIN_KEYWORDS_CS = ["PER", "ROE", "PBR"]


# ─────────────────────────────── JAPAN ───────────────────────────────

_JP_KEYWORDS = [
    # 核心词
    "日本株", "株式投資", "日経平均", "投資戦略",
    # 市场行情
    "日経225", "TOPIX", "東証", "マザーズ", "相場展望", "テクニカル分析",
    # 交易实战
    "デイトレード", "スイングトレード", "FX", "信用取引", "チャート分析",
    # 制度/税务
    "NISA", "新NISA", "iDeCo", "配当金", "株主優待", "確定申告",
    # 宏观经济
    "日銀", "金融政策", "金利", "為替", "円安", "円高",
    # 个股/不动产/暗号
    "決算", "PER", "成長株", "配当利回り", "不動産投資", "REIT", "暗号資産", "ビットコイン",
]

_JP_NATIVE = [
    "株", "投資", "経済", "金融", "資金", "証券", "財",
    "トレード", "取引", "相場", "為替", "円", "ドル",
    "配当", "優待", "決算", "銘柄", "ビットコイン", "暗号", "仮想通貨",
    "マーケット", "株価", "指数", "日経", "マザーズ",
    "利上げ", "利下げ", "金利", "インフレ", "デフレ", "政策",
    "バフェット", "ウォーレン", "ソロス", "ダリオ",
    "騰落", "買い", "売り", "暴落", "暴騰", "急騰", "高騰", "急落",
    "金融庁", "減税", "増税", "年金", "賃上げ",
    "景気", "不況", "好況", "リセッション",
    "為替介入", "財務省", "財務相", "日銀", "黒田", "植田",
    "米国株", "中国株", "半導体", "エヌビディア", "テスラ", "アップル",
    "NYダウ", "ダウ平均",
]

_JP_LATIN_CI = [
    "FX", "ETF", "IPO", "GDP", "CPI", "FOMC", "FRB", "ECB",
    "NISA", "iDeCo", "REIT", "NASDAQ", "JASDAQ", "TOPIX",
    "TSMC", "NVIDIA", "nikkei", "dow", "bitcoin", "S&P500", "S&P",
    "dividend", "shareholder", "earnings", "investor", "investing",
    "investment", "portfolio", "equity",
]

_JP_OFFICIAL = [
    # 政府・公共機関（财经导向，全面信任，不过滤）
    {"name": "日本銀行",                 "channel_id": "UC32Yu7NyStgmKYsXvYofPvQ"},
    {"name": "財務省",                   "channel_id": "UCBBBgFnML-9hLHa8tk3506g"},
    {"name": "金融庁",                   "channel_id": "UCpIgZIDc-ptkZZTvzqlwGQg"},
    {"name": "日本取引所グループ JPX",    "channel_id": "UCnZA74T8a8dEbavWRq8F2nA"},
    {"name": "経済産業省",               "channel_id": "UCAMvYSb3oO7oQpcaHZQYv7A"},
    # 権威ある経済・金融メディア／証券会社（专注财经，不过滤）
    {"name": "日経CNBC",                 "channel_id": "UClVsQnfs-jKkjKmUKUHnT2g"},
    {"name": "トウシル（楽天証券）",      "channel_id": "UC5BiTvy2Ni2MyigJPspjhOA"},
    {"name": "ストックボイス",           "channel_id": "UCgYt_yLa5ZVq7e_4Dzes8DQ"},
    {"name": "東洋経済オンライン",        "channel_id": "UCN36kFB7Lh4tptI4rsy5vFw"},
    {"name": "SBI証券",                  "channel_id": "UCQHZXj_ZXCHuwWLiHHahetQ"},
    # 综合新闻 / 政治为主（含非财经内容，需按关键词过滤）
    {"name": "ロイター日本",             "channel_id": "UCpC6ZVYT8-SxVb9zIcPDOTA", "filter": True},
    {"name": "首相官邸",                 "channel_id": "UCogK43-0HpBQXPahOswXJ0g", "filter": True},
    # 証券会社（专注财经，不过滤）
    {"name": "マネックス証券",           "channel_id": "UCTuTMd_xFwEhapfhv6kFDig"},
    {"name": "日経ポッドキャスト",       "channel_id": "UCa5GTH97HPtpXNuysWvWL_A"},
    # 経済・ビジネス動画メディア（一般ビジネス内容も含むため要フィルタ）
    {"name": "PIVOT",                    "channel_id": "UC8yHePe_RgUBE-waRWy6olw", "filter": True},
    {"name": "ReHacQ−リハック−",         "channel_id": "UCG_oqDSlIYEspNpd2H4zWhw", "filter": True},
    {"name": "テレ東BIZ",                "channel_id": "UCkKVQ_GNjd8FbAuT6xDcWgg", "filter": True},
]


# ─────────────────────────────── KOREA ───────────────────────────────

_KR_KEYWORDS = [
    # 핵심
    "주식", "주식투자", "투자", "증시", "코스피",
    # 시장 행정
    "코스닥", "증시전망", "시황", "기술적분석", "차트분석", "급등주",
    # 실전 매매
    "단타", "스윙투자", "데이트레이딩", "해외주식", "미국주식", "선물옵션",
    # 제도/세금
    "연금저축", "ISA", "IRP", "배당금", "배당주", "양도소득세",
    # 거시경제
    "한국은행", "기준금리", "금리", "환율", "원달러환율", "인플레이션",
    # 종목/부동산/코인
    "실적발표", "성장주", "부동산투자", "리츠", "비트코인", "코인", "가상자산",
    "삼성전자", "반도체", "엔비디아",
]

_KR_NATIVE = [
    "주식", "투자", "증시", "코스피", "코스닥", "증권", "펀드", "금융", "경제",
    "배당", "환율", "금리", "채권", "부동산", "리츠", "비트코인", "코인",
    "가상자산", "암호화폐", "반도체", "실적", "한국은행", "기준금리", "원달러",
    "나스닥", "다우", "매수", "매도", "급등", "급락", "상한가", "하한가",
    "시황", "재테크", "연금", "달러", "엔화", "유가", "물가", "인플레이션",
    "버핏", "워런", "테슬라", "엔비디아", "삼성전자",
]

_KR_LATIN_CI = [
    "FX", "ETF", "ETN", "IPO", "GDP", "CPI", "FOMC", "FRB", "ECB",
    "KOSPI", "KOSDAQ", "REIT", "NASDAQ", "ISA", "IRP",
    "TSMC", "NVIDIA", "bitcoin", "dow", "S&P500", "S&P",
    "dividend", "earnings", "investor", "investing", "investment",
    "portfolio", "equity",
]

_KR_OFFICIAL = [
    # 정부·공공기관 (전면 신뢰, 필터 없음)
    {"name": "한국은행",          "channel_id": "UCyK8niZNIfBTgRNkuURdoXA"},
    {"name": "한국거래소 KRX",     "channel_id": "UCS9GDeqpgGtDYy_Nx8opCZw"},
    {"name": "기획재정부",        "channel_id": "UCnrPF6de3KuHZy3c2ZkqcMA"},
    {"name": "금융위원회",        "channel_id": "UCuJz-PXNMdWQr6TNM4htENw"},
    # 금융·증권 미디어 / 증권사 (재경 전문, 필터 없음)
    {"name": "한국경제TV",         "channel_id": "UCF8AeLlUbEpKju6v1H6p8Eg"},
    {"name": "삼성증권",          "channel_id": "UCq7h8qFlHN5FL_T6waKZllw"},
    # 정부 금융감독 + 대형 증권사 + 인기 경제 미디어 (내용량 보강)
    # (미래에셋/NH투자증권/한국투자증권은 유튜브가 비활성 — RSS 비거나 수개월~수년
    #  정지 상태라 제외했다. 활성 증권사인 삼성/키움/KB만 유지.)
    {"name": "금융감독원 FSS",     "channel_id": "UCjA-tHJ2xLwZRXzqXq0UaqA"},
    {"name": "키움증권",          "channel_id": "UCZW1d7B2nYqQUiTiOnkirrQ"},
    {"name": "KB증권",           "channel_id": "UCD0k4Kq7SJROxxV-9N5v8IA"},
    {"name": "삼프로TV",          "channel_id": "UChlv4GSd7OQl3js-jkLOnFA"},
    # 종합 경제(투자 외 시사도 있어 필터)
    {"name": "슈카월드",          "channel_id": "UCsJ6RuBiTVWRX156FVbeaGg", "filter": True},
]


# ───────────────────────────── SINGAPORE ─────────────────────────────

_SG_KEYWORDS = [
    # core local
    "Singapore stocks", "SGX", "STI", "Straits Times Index", "Singapore REITs",
    "Singapore dividend stocks", "CPF investment", "Singapore Savings Bonds",
    "Singapore T-bills", "Singapore investing", "stock market Singapore",
    # local blue chips / banks
    "DBS stock", "OCBC stock", "UOB stock", "Singapore property", "Singapore bonds",
    # macro / authority
    "MAS monetary policy", "Singapore economy", "passive income Singapore",
    # cross-market (Singapore investors follow US heavily)
    "ETF investing", "US stocks", "S&P500", "Nasdaq", "Federal Reserve",
    "interest rates", "bitcoin", "dividend investing",
]

# Singapore finance content is English, so there are no native-script
# substring keywords — recognition relies on the (richer) Latin-token vocab.
_SG_NATIVE: list[str] = []

_SG_LATIN_CI = [
    # acronyms / indices / local instruments
    "FX", "ETF", "ETFs", "IPO", "GDP", "CPI", "FOMC", "FRB", "ECB", "Fed",
    "REIT", "REITs", "SGX", "STI", "CPF", "MAS", "SRS", "NASDAQ", "S&P500", "S&P",
    "DBS", "OCBC", "UOB", "bitcoin", "crypto",
    # English finance vocabulary (whole-token matched; plural "s" tolerated)
    "stock", "stocks", "shares", "dividend", "dividends", "investing",
    "investment", "investor", "portfolio", "equity", "equities", "bond", "bonds",
    "yield", "earnings", "valuation", "brokerage", "blue chip", "recession",
    "inflation",
]

_SG_OFFICIAL = [
    # central bank / exchange (trusted, no filter)
    {"name": "Monetary Authority of Singapore", "channel_id": "UC4EZ3SeI-rKff-TCXuFqxCg"},
    {"name": "SGX Group",                       "channel_id": "UCaurkyabSDD8bgrSqUyVhyg"},
    # finance media — BT is a finance daily but its YouTube feed mixes in general
    # news (earthquakes, politics), so filter to finance titles/descriptions.
    {"name": "The Business Times",              "channel_id": "UC0GP1HDhGZTLih7B89z_cTg", "filter": True},
    # general news (needs finance keyword filter)
    {"name": "CNA",                             "channel_id": "UC83jt4dlz1Gjl58fzQrrKZg", "filter": True},
    # investing/finance media (trusted). Money FM is a pure business/finance
    # radio station, so it's trusted — its titles (interview names) rarely match
    # plain stock keywords, so filtering would drop almost everything.
    # (Financial Horse dropped: its YouTube has been dormant ~4 years.)
    {"name": "The Smart Investor",              "channel_id": "UC9VbZ3SVG48lg8Zw6H-XPaw"},
    {"name": "MONEY FM 89.3",                   "channel_id": "UCKQ_ev3_C_V0zPn-9PDrL4g"},
    # general news (needs finance keyword filter)
    {"name": "The Straits Times",               "channel_id": "UC4p_I9eiRewn2KoU-nawrDg", "filter": True},
]


# ─────────────────────────────── REGISTRY ───────────────────────────────
#
# ``lang_regex`` selects the script that earns the local-language scoring bonus.
# ``channel_search_term`` seeds the YouTube per-channel deep-scrape.

REGIONS: dict[str, dict] = {
    "jp": {
        "id": "jp",
        "name": "日本",
        "flag": "🇯🇵",
        "platforms": ["youtube", "official", "niconico"],
        "channel_search_term": "投資",
        "lang_regex": r"[぀-ヿ一-鿿㐀-䶿]",   # kana + kanji
        "keywords": _JP_KEYWORDS,
        "native_keywords": _JP_NATIVE,
        "latin_ci": _JP_LATIN_CI,
        "latin_cs": LATIN_KEYWORDS_CS,
        "official_channels": _JP_OFFICIAL,
    },
    "kr": {
        "id": "kr",
        "name": "韩国",
        "flag": "🇰🇷",
        "platforms": ["youtube", "official"],
        "channel_search_term": "투자",
        "lang_regex": r"[가-힣]",              # Hangul syllables
        "keywords": _KR_KEYWORDS,
        "native_keywords": _KR_NATIVE,
        "latin_ci": _KR_LATIN_CI,
        "latin_cs": LATIN_KEYWORDS_CS,
        "official_channels": _KR_OFFICIAL,
    },
    "sg": {
        "id": "sg",
        "name": "新加坡",
        "flag": "🇸🇬",
        "platforms": ["youtube", "official"],
        "channel_search_term": "stocks",
        "lang_regex": r"[A-Za-z]",             # English (Latin)
        "keywords": _SG_KEYWORDS,
        "native_keywords": _SG_NATIVE,
        "latin_ci": _SG_LATIN_CI,
        "latin_cs": LATIN_KEYWORDS_CS,
        "official_channels": _SG_OFFICIAL,
    },
}

# Display order for the UI region switcher.
REGION_ORDER = ["jp", "kr", "sg"]


def get_region(region: str | None) -> dict:
    """Return the config dict for *region*, falling back to the default."""
    return REGIONS.get(region or DEFAULT_REGION, REGIONS[DEFAULT_REGION])
