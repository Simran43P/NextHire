"""
Where to go and learn a missing skill.

Naming a gap without pointing anywhere is half an answer, but inventing URLs is
worse than saying nothing - a broken link in a tool that exists to be trusted
costs more than the convenience is worth. So there are exactly two kinds of
link here and both are safe by construction:

1. **Official documentation** for skills common enough to be worth curating by
   hand. These are the canonical homes maintained by the projects themselves.
2. **A search**, for everything else. A search URL is a query parameter on a
   host that exists; it cannot 404 and it cannot go stale.

Nothing here is a guess at a tutorial that may or may not exist.
"""

from __future__ import annotations

from urllib.parse import quote_plus

# Canonical documentation for the skills that actually recur in postings.
# Deliberately small and deliberately official - every entry is a project's own
# front door, not a third-party course that may disappear.
OFFICIAL_DOCS: dict[str, tuple[str, str]] = {
    "docker": ("Docker documentation", "https://docs.docker.com/"),
    "kubernetes": ("Kubernetes documentation", "https://kubernetes.io/docs/home/"),
    "terraform": ("Terraform documentation", "https://developer.hashicorp.com/terraform/docs"),
    "react": ("React documentation", "https://react.dev/learn"),
    "typescript": ("TypeScript handbook", "https://www.typescriptlang.org/docs/"),
    "python": ("Python documentation", "https://docs.python.org/3/"),
    "django": ("Django documentation", "https://docs.djangoproject.com/"),
    "flask": ("Flask documentation", "https://flask.palletsprojects.com/"),
    "fastapi": ("FastAPI documentation", "https://fastapi.tiangolo.com/"),
    "postgresql": ("PostgreSQL documentation", "https://www.postgresql.org/docs/"),
    "mysql": ("MySQL documentation", "https://dev.mysql.com/doc/"),
    "mongodb": ("MongoDB documentation", "https://www.mongodb.com/docs/"),
    "redis": ("Redis documentation", "https://redis.io/docs/latest/"),
    "kafka": ("Apache Kafka documentation", "https://kafka.apache.org/documentation/"),
    "elasticsearch": ("Elasticsearch documentation", "https://www.elastic.co/docs"),
    "graphql": ("GraphQL documentation", "https://graphql.org/learn/"),
    "git": ("Pro Git book", "https://git-scm.com/doc"),
    "node.js": ("Node.js documentation", "https://nodejs.org/docs/latest/api/"),
    "nodejs": ("Node.js documentation", "https://nodejs.org/docs/latest/api/"),
    "spring boot": ("Spring Boot documentation", "https://docs.spring.io/spring-boot/"),
    "hibernate": ("Hibernate documentation", "https://hibernate.org/orm/documentation/"),
    "java": ("Java documentation", "https://docs.oracle.com/en/java/"),
    "go": ("Go documentation", "https://go.dev/doc/"),
    "rust": ("The Rust book", "https://doc.rust-lang.org/book/"),
    "pytorch": ("PyTorch documentation", "https://pytorch.org/docs/stable/index.html"),
    "tensorflow": ("TensorFlow documentation", "https://www.tensorflow.org/learn"),
    "pandas": ("pandas documentation", "https://pandas.pydata.org/docs/"),
    "numpy": ("NumPy documentation", "https://numpy.org/doc/stable/"),
    "scikit-learn": ("scikit-learn documentation", "https://scikit-learn.org/stable/"),
    "aws": ("AWS documentation", "https://docs.aws.amazon.com/"),
    "azure": ("Azure documentation", "https://learn.microsoft.com/azure/"),
    "gcp": ("Google Cloud documentation", "https://cloud.google.com/docs"),
    "linux": ("The Linux Documentation Project", "https://tldp.org/"),
    "sql": ("SQL tutorial (PostgreSQL)", "https://www.postgresql.org/docs/current/tutorial.html"),
    "ci/cd": ("GitHub Actions documentation", "https://docs.github.com/actions"),
    "jenkins": ("Jenkins documentation", "https://www.jenkins.io/doc/"),
    "grpc": ("gRPC documentation", "https://grpc.io/docs/"),
    "celery": ("Celery documentation", "https://docs.celeryq.dev/"),
}


def _search(skill: str) -> dict[str, str]:
    """
    A search for the skill.

    Always valid: it is a query parameter on a host that exists, so it cannot
    rot the way a hand-picked tutorial link does.
    """
    return {
        "label": f"Search for {skill} tutorials",
        "url": f"https://duckduckgo.com/?q={quote_plus(f'learn {skill} tutorial')}",
        "kind": "search",
    }


def for_skill(skill: str) -> list[dict[str, str]]:
    """Return links for one skill: official docs where known, plus a search."""
    key = (skill or "").strip().lower()
    if not key:
        return []

    links: list[dict[str, str]] = []
    entry = OFFICIAL_DOCS.get(key)

    if entry is None:
        # Tolerate the phrasing a posting actually uses - "Docker containers",
        # "advanced SQL" - without matching a substring of an unrelated word.
        for name, candidate in OFFICIAL_DOCS.items():
            if key == name or key.startswith(f"{name} ") or key.endswith(f" {name}"):
                entry = candidate
                break

    if entry is not None:
        links.append({"label": entry[0], "url": entry[1], "kind": "docs"})

    links.append(_search(skill))
    return links
