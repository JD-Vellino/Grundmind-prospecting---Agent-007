from __future__ import annotations

import json
import re

from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_CONFIG_DIR = (
    BASE_DIR / "company_configs"
)


@dataclass(frozen=True)
class SourcePolicy:
    official_domains: tuple[str, ...]
    official_source_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    aliases: tuple[str, ...]
    research_identity: str
    excluded_domains: tuple[str, ...]
    source_policies: dict[str, SourcePolicy]

    def policy(
        self,
        signal: str,
    ) -> SourcePolicy:
        try:
            return self.source_policies[signal]

        except KeyError as exc:
            raise KeyError(
                f"No source policy configured for "
                f"{self.name!r}, signal {signal!r}."
            ) from exc


LOGITECH = CompanyConfig(
    name="Logitech",
    aliases=(
        "logitech",
        "logitech international",
        "logitech international sa",
    ),
    research_identity=(
        "Logitech International, the technology "
        "and computer-peripherals company whose "
        "official website is logitech.com."
    ),
    excluded_domains=(),
    source_policies={
        "ai_hiring": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
            ),
        ),
        "ai_deployment": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
            ),
            official_source_prefixes=(
                "https://s1.q4cdn.com/104539020/",
            ),
        ),
        "ai_value_roi": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
            ),
            official_source_prefixes=(
                "https://s1.q4cdn.com/104539020/",
            ),
        ),
        "organisational_fit": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
                "sec.gov",
            ),
            official_source_prefixes=(
                "https://s1.q4cdn.com/104539020/",
            ),
        ),
        "commercial_opportunity": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
            ),
            official_source_prefixes=(
                "https://s1.q4cdn.com/104539020/",
            ),
        ),
        "account_brief": SourcePolicy(
            official_domains=(
                "logitech.com",
                "logitech.wd5.myworkdayjobs.com",
            ),
            official_source_prefixes=(
                "https://s1.q4cdn.com/104539020/",
            ),
        ),
    },
)


STATIC_COMPANIES = (
    LOGITECH,
)


def normalize_name(
    value: str,
) -> str:
    return " ".join(
        value.strip().lower().split()
    )


def slugify(
    value: str,
) -> str:
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.lower(),
    )

    return slug.strip("-")


def config_to_dict(
    config: CompanyConfig,
) -> dict:
    return {
        "name": config.name,
        "aliases": list(config.aliases),
        "research_identity": (
            config.research_identity
        ),
        "excluded_domains": list(
            config.excluded_domains
        ),
        "source_policies": {
            signal: {
                "official_domains": list(
                    policy.official_domains
                ),
                "official_source_prefixes": list(
                    policy.official_source_prefixes
                ),
            }
            for signal, policy
            in config.source_policies.items()
        },
    }


def config_from_dict(
    data: dict,
) -> CompanyConfig:

    policies = {}

    for signal, policy in data.get(
        "source_policies",
        {},
    ).items():

        policies[signal] = SourcePolicy(
            official_domains=tuple(
                policy.get(
                    "official_domains",
                    [],
                )
            ),
            official_source_prefixes=tuple(
                policy.get(
                    "official_source_prefixes",
                    [],
                )
            ),
        )

    return CompanyConfig(
        name=data["name"],
        aliases=tuple(
            data.get(
                "aliases",
                [],
            )
        ),
        research_identity=data.get(
            "research_identity",
            data["name"],
        ),
        excluded_domains=tuple(
            data.get(
                "excluded_domains",
                [],
            )
        ),
        source_policies=policies,
    )


def load_runtime_configs() -> list[CompanyConfig]:

    if not RUNTIME_CONFIG_DIR.exists():
        return []

    configs = []

    for path in sorted(
        RUNTIME_CONFIG_DIR.glob("*.json")
    ):
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            configs.append(
                config_from_dict(data)
            )

        except Exception as exc:
            raise ValueError(
                f"Invalid runtime company config: "
                f"{path.name}: {exc}"
            ) from exc

    return configs


def save_company_config(
    config: CompanyConfig,
) -> Path:

    RUNTIME_CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        RUNTIME_CONFIG_DIR
        / f"{slugify(config.name)}.json"
    )

    path.write_text(
        json.dumps(
            config_to_dict(config),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def get_company_config(
    company: str,
) -> CompanyConfig:

    normalized = normalize_name(
        company
    )

    companies = (
        list(STATIC_COMPANIES)
        + load_runtime_configs()
    )

    for config in companies:

        names = {
            normalize_name(config.name),
            *(
                normalize_name(alias)
                for alias in config.aliases
            ),
        }

        if normalized in names:
            return config

    raise ValueError(
        f"No Agent 007 company configuration "
        f"exists for {company!r}."
    )
