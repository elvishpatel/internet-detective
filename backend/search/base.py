from dataclasses import dataclass, asdict

@dataclass
class Source:
    url: str
    title: str
    snippet: str
    domain: str
    source_type: str = "web"
    published_at: str | None = None
    discovered_by: str = "web"
    def json(self): return asdict(self)
