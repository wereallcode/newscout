import sqlite3
from dataclasses import dataclass

from newscout import db


@dataclass(frozen=True)
class Preset:
    name: str
    relevance: str
    sources: dict[str, str]


CNBC = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id="

PRESETS = (
    Preset(
        "Turkish News",
        "Keep politics, economy, world and technology news.\n"
        "Drop sports, celebrity gossip and advertising.",
        {
            "https://www.aa.com.tr/tr/rss/default?cat=guncel": "Anadolu Ajansı",
            "https://feeds.bbci.co.uk/turkce/rss.xml": "BBC Türkçe",
            "https://www.cumhuriyet.com.tr/rss/son_dakika.xml": "Cumhuriyet",
            "https://rss.dw.com/rdf/rss-tur-all": "DW Türkçe",
            "https://www.diken.com.tr/feed/": "Diken",
            "https://tr.euronews.com/rss": "Euronews Türkçe",
            "https://www.haberturk.com/rss/kategori/gundem.xml": "Habertürk",
            "https://www.hurriyet.com.tr/rss/gundem": "Hürriyet Gündem",
            "https://www.hurriyet.com.tr/rss/teknoloji": "Hürriyet Teknoloji",
            "https://medyascope.tv/feed/": "Medyascope",
            "https://www.milliyet.com.tr/rss/rssnew/gundemrss.xml": "Milliyet",
            "https://www.ntv.com.tr/gundem.rss": "NTV",
            "https://www.sabah.com.tr/rss/gundem.xml": "SABAH",
            "https://www.sozcu.com.tr/feeds-rss-category-gundem": "Sözcü",
            "https://www.yenisafak.com/rss?xml=gundem": "Yeni Şafak",
        },
    ),
    Preset(
        "Global Finance",
        "Keep finance, markets, business and economy news.\n"
        "Drop advertising and sponsored content.",
        {
            f"{CNBC}100003114": "CNBC",
            f"{CNBC}20910258": "CNBC Economy",
            "https://feeds.content.dowjones.io/public/rss/mw_topstories": "MarketWatch",
            "https://feeds.content.dowjones.io/public/rss/mw_marketpulse": "MarketWatch Pulse",
            "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain": "WSJ Markets",
            "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness": "WSJ Business",
            "https://www.ft.com/markets?format=rss": "Financial Times",
            "https://www.theguardian.com/business/rss": "The Guardian Business",
            "https://feeds.bbci.co.uk/news/business/rss.xml": "BBC Business",
            "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml": "NYT Business",
            "https://www.investing.com/rss/news.rss": "Investing.com",
            "https://seekingalpha.com/market_currents.xml": "Seeking Alpha",
            "https://fortune.com/feed/": "Fortune",
            "https://markets.businessinsider.com/rss/news": "Business Insider",
            "https://www.economist.com/finance-and-economics/rss.xml": "The Economist",
            "https://www.forbes.com/business/feed/": "Forbes",
            "https://www.federalreserve.gov/feeds/press_all.xml": "Federal Reserve",
            "https://www.ecb.europa.eu/rss/press.html": "European Central Bank",
        },
    ),
    Preset(
        "Gaming",
        "Keep video game news: releases, updates, reviews, industry and hardware.\n"
        "Drop deals, giveaways, guides and advertising.",
        {
            "https://www.ign.com/rss/articles/feed": "IGN",
            "https://www.gamespot.com/feeds/news/": "GameSpot",
            "https://www.polygon.com/rss/index.xml": "Polygon",
            "https://kotaku.com/rss": "Kotaku",
            "https://www.eurogamer.net/feed/news": "Eurogamer",
            "https://www.pcgamer.com/rss/": "PC Gamer",
            "https://www.rockpapershotgun.com/feed/news": "Rock Paper Shotgun",
            "https://www.gamesradar.com/rss/": "GamesRadar+",
            "https://www.vg247.com/feed": "VG247",
            "https://www.destructoid.com/feed/": "Destructoid",
            "https://www.gematsu.com/feed": "Gematsu",
            "https://www.siliconera.com/feed/": "Siliconera",
            "https://www.nintendolife.com/feeds/latest": "Nintendo Life",
            "https://www.pushsquare.com/feeds/latest": "Push Square",
            "https://www.purexbox.com/feeds/latest": "Pure Xbox",
            "https://www.purenintendo.com/feed/": "Pure Nintendo",
            "https://blog.playstation.com/feed/": "PlayStation Blog",
            "https://news.xbox.com/en-us/feed/": "Xbox Wire",
            "https://www.gamedeveloper.com/rss.xml": "Game Developer",
            "https://www.gamesindustry.biz/feed": "GamesIndustry.biz",
            "https://www.videogameschronicle.com/feed/": "VGC",
            "https://www.dualshockers.com/feed/": "DualShockers",
            "https://www.thegamer.com/feed/": "TheGamer",
            "https://gamerant.com/feed/": "Game Rant",
            "https://www.pcgamesn.com/mainrss.xml": "PCGamesN",
            "https://www.escapistmagazine.com/feed/": "The Escapist",
            "https://www.gameinformer.com/news.xml": "Game Informer",
            "https://www.theverge.com/rss/games/index.xml": "The Verge Gaming",
            "https://arstechnica.com/gaming/feed/": "Ars Technica Gaming",
            "https://www.techradar.com/rss/news/gaming": "TechRadar Gaming",
            "https://www.shacknews.com/feed/rss": "Shacknews",
            "https://www.rpgsite.net/feed": "RPG Site",
            "https://www.gamingbolt.com/feed": "GamingBolt",
            "https://www.dexerto.com/feed/": "Dexerto",
            "https://www.mmorpg.com/rss": "MMORPG.com",
            "https://massivelyop.com/feed/": "Massively Overpowered",
            "https://www.pocketgamer.com/rss/": "Pocket Gamer",
            "https://toucharcade.com/feed/": "TouchArcade",
            "https://www.godisageek.com/feed/": "God is a Geek",
            "https://www.thesixthaxis.com/feed/": "TheSixthAxis",
        },
    ),
)


# Installed once on the first run, so a preset group you delete stays deleted.
def install(conn: sqlite3.Connection) -> None:
    if db.settings.get(conn, "presets_installed"):
        return
    for preset in PRESETS:
        try:
            group_id = db.groups.add(conn, preset.name, preset.relevance)
        except db.groups.DuplicateGroup:
            continue
        db.groups.set_enabled(conn, group_id, False)
        for url, name in preset.sources.items():
            try:
                db.sources.add(conn, url, name=name, group_id=group_id)
            except db.sources.DuplicateSource:
                pass
    db.settings.put(conn, "presets_installed", "1")
