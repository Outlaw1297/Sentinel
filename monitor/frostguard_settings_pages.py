"""Frostguard operator-panel pages from ConfigurationKeyEnum.

The desktop app groups keys by ConfigCategory, not by the first word of the
key. BOOL_BANK is Shops, RESEARCH_* is City, and legacy keys stay hidden.
"""

from __future__ import annotations

# Pages in the order Frostguard's operator panel declares them.
PAGES: tuple[tuple[str, str, str], ...] = (
    ("alliance", "Alliance", "Autojoin, championship, chests, help, mobilization, shop, and tech."),
    ("analytics", "Analytics", "Diagnostics Frostguard records for this workspace."),
    ("city", "City", "Survivors, furnace upgrades, and research."),
    ("dailies", "Dailies", "Arena, daily missions, mail, and the storehouse."),
    ("events", "Events", "Bear trap, beasts, polar terror, rallies, fishing, and trucks."),
    ("experts", "Experts", "Expert skills and troop assignments."),
    ("gathering", "Gathering", "Resource marches, levels, and gather speed."),
    ("intel", "Intel", "Intel missions, beasts, camps, and exploration."),
    ("pets", "Pets", "Life essence, pet adventure, and pet skills."),
    ("shops", "Shops", "Bank, crystal lab, exploration, recruitment, nomadic merchant, and VIP."),
    ("system", "System", "Emulator, autostart, idle behavior, and how many instances run at once."),
    ("testing", "Testing", "Character creation, tutorial skip, and profile time limits."),
    ("training", "Training", "Troop training and promotion."),
)

_PAGE_INDEX = {page_id: index for index, (page_id, _title, _desc) in enumerate(PAGES)}
_PAGE_TITLE = {page_id: title for page_id, title, _desc in PAGES}
_PAGE_DESC = {page_id: desc for page_id, _title, desc in PAGES}

# Keys retained only so old profiles still load. They are not on the panel.
_LEGACY_KEYS = frozenset(
    {
        "ARENA_TASK_PLAYER_STATE_INT",
        "ARENA_TASK_PROTECT_ALLIANCE_BOOL",
        "GIFT_CODE_STATE_JSON",
    }
)

# Runtime bookkeeping and swipe calibration, not operator settings.
_INTERNAL_KEYS = frozenset(
    {
        "STATISTICS_JSON_STRING",
        "ANALYTICS_ID_STRING",
        "GATHER_LAST_RECALL_TIME_STRING",
        "LIFE_ESSENCE_CONSECUTIVE_FAILURES_INT",
        "LIFE_ESSENCE_NEXT_SCROLL_TIME_STRING",
        "PET_SKILL_GATHERING_LAST_DEPLOYED_AT_STRING",
        "VIP_NEXT_MONTHLY_BUY_TIME_STRING",
        "TRAIN_MINISTRY_APPOINTMENT_TIME_LONG",
    }
)

_PAGES_BY_KEY: dict[str, str] = {}


def _add(page: str, *keys: str) -> None:
    for key in keys:
        _PAGES_BY_KEY[key] = page


_add(
    "analytics",
    "ANALYTICS_ENABLED_BOOL",
    "HIDE_ANALYTICS_LOGS_BOOL",
)
_add(
    "alliance",
    "ALLIANCE_CHAMPIONSHIP_BOOL",
    "ALLIANCE_CHAMPIONSHIP_INFANTRY_PERCENTAGE_INT",
    "ALLIANCE_CHAMPIONSHIP_LANCERS_PERCENTAGE_INT",
    "ALLIANCE_CHAMPIONSHIP_MARKSMANS_PERCENTAGE_INT",
    "ALLIANCE_CHAMPIONSHIP_OVERRIDE_DEPLOY_BOOL",
    "ALLIANCE_CHAMPIONSHIP_POSITION_STRING",
    "ALLIANCE_CHAMPIONSHIP_FLAG_STRING",
    "ALLIANCE_AUTOJOIN_BOOL",
    "ALLIANCE_AUTOJOIN_QUEUES_INT",
    "ALLIANCE_AUTOJOIN_USE_ALL_TROOPS_BOOL",
    "ALLIANCE_AUTOJOIN_USE_PREDEFINED_FORMATION_BOOL",
    "ALLIANCE_CHESTS_BOOL",
    "ALLIANCE_CHESTS_OFFSET_INT",
    "ALLIANCE_HELP_BOOL",
    "ALLIANCE_HONOR_CHEST_BOOL",
    "ALLIANCE_LIFE_ESSENCE_BOOL",
    "ALLIANCE_LIFE_ESSENCE_OFFSET_INT",
    "ALLIANCE_MOBILIZATION_AUTO_ACCEPT_BOOL",
    "ALLIANCE_MOBILIZATION_BOOL",
    "ALLIANCE_MOBILIZATION_BUILD_SPEEDUPS_BOOL",
    "ALLIANCE_MOBILIZATION_BUY_PACKAGE_BOOL",
    "ALLIANCE_MOBILIZATION_CHIEF_GEAR_CHARM_BOOL",
    "ALLIANCE_MOBILIZATION_CHIEF_GEAR_SCORE_BOOL",
    "ALLIANCE_MOBILIZATION_DEFEAT_BEASTS_BOOL",
    "ALLIANCE_MOBILIZATION_FIRE_CRYSTAL_BOOL",
    "ALLIANCE_MOBILIZATION_GATHER_RESOURCES_BOOL",
    "ALLIANCE_MOBILIZATION_HERO_GEAR_STONE_BOOL",
    "ALLIANCE_MOBILIZATION_MINIMUM_POINTS_120_INT",
    "ALLIANCE_MOBILIZATION_MINIMUM_POINTS_200_INT",
    "ALLIANCE_MOBILIZATION_MYTHIC_SHARD_BOOL",
    "ALLIANCE_MOBILIZATION_RALLY_BOOL",
    "ALLIANCE_MOBILIZATION_REWARDS_PERCENTAGE_STRING",
    "ALLIANCE_MOBILIZATION_TRAIN_TROOPS_BOOL",
    "ALLIANCE_MOBILIZATION_TRAINING_SPEEDUPS_BOOL",
    "ALLIANCE_MOBILIZATION_USE_GEMS_BOOL",
    "ALLIANCE_MOBILIZATION_USE_GEMS_FOR_ACCEPT_BOOL",
    "ALLIANCE_MOBILIZATION_USE_SPEEDUPS_BOOL",
    "ALLIANCE_PET_TREASURE_BOOL",
    "ALLIANCE_SHOP_ENABLED_BOOL",
    "ALLIANCE_SHOP_MIN_COINS_INT",
    "ALLIANCE_SHOP_MIN_COINS_TO_ACTIVATE_INT",
    "ALLIANCE_SHOP_MIN_PERCENTAGE_INT",
    "ALLIANCE_SHOP_PRIORITIES_STRING",
    "ALLIANCE_TECH_BOOL",
    "ALLIANCE_TECH_OFFSET_INT",
    "ALLIANCE_TRIUMPH_BOOL",
    "ALLIANCE_TRIUMPH_OFFSET_INT",
)
_add(
    "city",
    "CITY_ACCEPT_NEW_SURVIVORS_BOOL",
    "CITY_ACCEPT_NEW_SURVIVORS_OFFSET_INT",
    "CITY_UPGRADE_FURNACE_BOOL",
    "CITY_UPGRADE_RESERVE_PRODUCTION_BOOL",
    "CITY_UPGRADE_CONSTRUCTION_LOCK_STRING",
    "CITY_UPGRADE_PRIORITISE_FURNACE_BOOL",
    "RESEARCH_BATTLE_BOOL",
    "RESEARCH_ECONOMY_BOOL",
    "RESEARCH_ENABLED_BOOL",
    "RESEARCH_GROWTH_BOOL",
    "RESEARCH_PRIORITIES_STRING",
)
_add(
    "dailies",
    "ARENA_TASK_ACTIVATION_TIME_STRING",
    "ARENA_TASK_BOOL",
    "ARENA_TASK_EXTRA_ATTEMPTS_INT",
    "ARENA_TASK_ATTACK_QUICK_DEPLOY_BOOL",
    "ARENA_TASK_SERVER_POLICY_STRING",
    "ARENA_TASK_ALLIANCE_POLICY_STRING",
    "ARENA_TASK_REFRESH_WITH_GEMS_BOOL",
    "DAILY_LABYRINTH_BOOL",
    "DAILY_MISSION_AUTO_SCHEDULE_BOOL",
    "DAILY_MISSION_BOOL",
    "DAILY_MISSION_OFFSET_INT",
    "MAIL_REWARDS_BOOL",
    "MAIL_REWARDS_OFFSET_INT",
    "STOREHOUSE_CHEST_BOOL",
    "STOREHOUSE_STAMINA_CLAIM_TIME_STRING",
)
_add(
    "events",
    "BEAR_TRAP_ACTIVE_PETS_BOOL",
    "BEAR_TRAP_CALL_RALLY_BOOL",
    "BEAR_TRAP_EVENT_BOOL",
    "BEAR_TRAP_ICON_PARTICIPATION_FALLBACK_BOOL",
    "BEAR_TRAP_JOIN_FLAG_INT",
    "BEAR_TRAP_JOIN_RALLY_BOOL",
    "BEAR_TRAP_NUMBER_INT",
    "BEAR_TRAP_PREPARATION_TIME_INT",
    "BEAR_TRAP_RALLY_FLAG_INT",
    "BEAR_TRAP_RECALL_TROOPS_BOOL",
    "BEAR_TRAP_TIMER_1_ENABLED_BOOL",
    "BEAR_TRAP_TIMER_1_BLOCK_RALLIES_BOOL",
    "BEAR_TRAP_TIMER_1_PAUSE_ALL_TASKS_BOOL",
    "BEAR_TRAP_SCHEDULE_DATETIME_STRING",
    "BEAR_TRAP_TIMER_2_ENABLED_BOOL",
    "BEAR_TRAP_TIMER_2_BLOCK_RALLIES_BOOL",
    "BEAR_TRAP_TIMER_2_PAUSE_ALL_TASKS_BOOL",
    "BEAR_TRAP_TIMER_2_SCHEDULE_DATETIME_STRING",
    "BEAST_HUNTING_ENABLED_BOOL",
    "BEAST_HUNTING_LEVEL_INT",
    "BEAST_HUNTING_MARCHES_INT",
    "STAMINA_RESERVE_INT",
    "BOOL_CHIEF_ORDER_PRODUCTIVITY_DAY",
    "BOOL_CHIEF_ORDER_RUSH_JOB",
    "BOOL_CHIEF_ORDER_URGENT_MOBILISATION",
    "FISHING_MINIGAME_ENABLED_BOOL",
    "FISHING_MAX_CASTS_INT",
    "FISHING_TARGET_CATCHES_INT",
    "FISHING_MAX_RESTARTS_INT",
    "FISHING_SHORT_HAUL_RESTART_ENABLED_BOOL",
    "FISHING_DARK_CORNER_ENABLED_BOOL",
    "FISHING_MAX_SPECIAL_CASTS_INT",
    "FISHING_USE_LANTERN_BOOL",
    "FISHING_USE_STABILIZER_BOOL",
    "FISHING_REQUIRE_SPECIAL_ITEMS_BOOL",
    "HERO_MISSION_EVENT_BOOL",
    "HERO_MISSION_FLAG_INT",
    "JOURNEY_OF_LIGHT_BOOL",
    "MERCENARY_EVENT_BOOL",
    "MERCENARY_FLAG_INT",
    "MYRIAD_BAZAAR_EVENT_BOOL",
    "POLAR_TERROR_ENABLED_BOOL",
    "POLAR_TERROR_LEVEL_INT",
    "POLAR_TERROR_HIGHEST_LEVEL_BOOL",
    "POLAR_TERROR_MARCH_1_FLAG_STRING",
    "POLAR_TERROR_MARCH_2_FLAG_STRING",
    "POLAR_TERROR_MARCH_3_FLAG_STRING",
    "POLAR_TERROR_MARCH_4_FLAG_STRING",
    "POLAR_TERROR_MARCH_5_FLAG_STRING",
    "POLAR_TERROR_MARCH_6_FLAG_STRING",
    "POLAR_TERROR_MARCHES_INT",
    "POLAR_TERROR_MODE_STRING",
    "POLAR_TERROR_USE_STAMINA_ITEMS_BOOL",
    "POLAR_TERROR_STAMINA_ITEM_RESERVE_INT",
    "RALLY_ENABLED_BOOL",
    "RALLY_MARCH_1_FLAG_STRING",
    "RALLY_MARCH_2_FLAG_STRING",
    "RALLY_MARCH_3_FLAG_STRING",
    "RALLY_MARCH_4_FLAG_STRING",
    "RALLY_MARCH_5_FLAG_STRING",
    "RALLY_MARCH_6_FLAG_STRING",
    "RALLY_MARCHES_INT",
    "RALLY_MODE_STRING",
    "RALLY_TARGET_STRING",
    "TEST_HOOK_LOOP_ENABLED_BOOL",
    "TUNDRA_TRUCK_ACTIVATION_TIME_BOOL",
    "TUNDRA_TRUCK_ACTIVATION_TIME_STRING",
    "TUNDRA_TRUCK_EVENT_BOOL",
    "TUNDRA_TRUCK_SSR_BOOL",
    "TUNDRA_TRUCK_USE_GEMS_BOOL",
    "TUNDRA_TREK_AUTOMATION_BOOL",
    "TUNDRA_TREK_SUPPLIES_BOOL",
)
_add(
    "experts",
    "EXPERT_AGNES_INTEL_BOOL",
    "EXPERT_ROMULUS_TAG_BOOL",
    "EXPERT_ROMULUS_TROOPS_BOOL",
    "EXPERT_ROMULUS_TROOPS_TYPE_STRING",
    "EXPERT_SKILL_TRAINING_ENABLED_BOOL",
    "EXPERT_SKILL_TRAINING_PRIORITIES_STRING",
)
_add(
    "gathering",
    "GATHER_ACTIVE_MARCH_QUEUE_INT",
    "GATHER_COAL_BOOL",
    "GATHER_COAL_LEVEL_INT",
    "GATHER_IRON_BOOL",
    "GATHER_IRON_LEVEL_INT",
    "GATHER_MEAT_BOOL",
    "GATHER_MEAT_LEVEL_INT",
    "GATHER_ONLY_FULL_RESOURCES_BOOL",
    "GATHER_DOWNGRADE_LEVEL_BOOL",
    "GATHER_REMOVE_HEROS_BOOL",
    "GATHER_NO_HERO_FALLBACK_BOOL",
    "GATHER_ROTATION_POOL",
    "GATHER_SPEED_BOOL",
    "GATHER_SPEED_BOOST_TYPE_STRING",
    "GATHER_TASK_BOOL",
    "GATHER_WOOD_BOOL",
    "GATHER_WOOD_LEVEL_INT",
)
_add(
    "intel",
    "INTEL_BEASTS_BOOL",
    "INTEL_BEASTS_EVENT_BOOL",
    "INTEL_BEASTS_FLAG_INT",
    "INTEL_BOOL",
    "INTEL_CAMP_BOOL",
    "INTEL_EXPLORATION_BOOL",
    "INTEL_FIRE_BEAST_BOOL",
    "INTEL_RECALL_GATHER_TROOPS_BOOL",
    "INTEL_SMART_PROCESSING_BOOL",
    "INTEL_USE_FLAG_BOOL",
)
_add(
    "pets",
    "LIFE_ESSENCE_BOOL",
    "LIFE_ESSENCE_BUY_WEEKLY_SCROLL_BOOL",
    "LIFE_ESSENCE_OFFSET_INT",
    "PET_ADVENTURE_OBSERVE_ONLY_BOOL",
    "PET_PERSONAL_TREASURE_BOOL",
    "PET_SKILL_FOOD_BOOL",
    "PET_SKILL_GATHERING_BOOL",
    "PET_SKILL_GATHERING_RESOURCE_STRING",
    "PET_SKILL_STAMINA_BOOL",
    "PET_SKILL_TREASURE_BOOL",
    "PET_SKILLS_BOOL",
)
_add(
    "shops",
    "BOOL_CRYSTAL_LAB_DAILY_DISCOUNTED_RFC",
    "BOOL_CRYSTAL_LAB_FC",
    "BOOL_DO_EXPLORATION",
    "DO_EXPLORATION_QUICK_DEPLOY_BOOL",
    "BOOL_EXPLORATION_CHEST",
    "BOOL_HERO_RECRUITMENT",
    "BOOL_MYSTERY_SHOP",
    "BOOL_MYSTERY_SHOP_250_HERO_WIDGET",
    "BOOL_MYSTERY_SHOP_250_SHARD",
    "BOOL_NOMADIC_MERCHANT",
    "BOOL_NOMADIC_MERCHANT_VIP_POINTS",
    "BOOL_VIP_POINTS",
    "INT_EXPLORATION_CHEST_OFFSET",
    "INT_WEEKLY_RFC",
    "VIP_MONTHLY_BUY_BOOL",
    "WAR_ACADEMY_TASK_BOOL",
    "BOOL_BANK",
    "INT_BANK_DELAY",
)
_add(
    "system",
    "AUTO_START_DELAY_MINUTES_INT",
    "AUTO_START_ENABLED_BOOL",
    "AUTO_START_MODE_STRING",
    "BOOL_DEBUG",
    "CURRENT_EMULATOR_STRING",
    "DESKTOP_SNAPSHOT_ENABLED_BOOL",
    "MISSING_TEMPLATE_SNAPSHOT_ENABLED_BOOL",
    "GAME_VERSION_STRING",
    "IDLE_BEHAVIOR_STRING",
    "STOP_BEHAVIOR_STRING",
    "STOP_BEHAVIOR_TELEGRAM_STRING",
    "LDPLAYER_PATH_STRING",
    "MAX_IDLE_TIME_INT",
    "MAX_RUNNING_EMULATORS_INT",
    "EMULATOR_LAUNCH_DELAY_MS_INT",
    "MEMU_PATH_STRING",
    "MUMU_PATH_STRING",
    "PROFILE_SWITCH_COOLDOWN_MS_INT",
    "TELEGRAM_BOT_ENABLED_BOOL",
)
_add(
    "testing",
    "CREATE_CHARACTER_ENABLED_BOOL",
    "CREATE_CHARACTER_MAX_AGE_MINUTES_INT",
    "CREATE_CHARACTER_SKIP_TUTORIAL_BOOL",
    "DUMMY_TASK_ENABLED_BOOL",
    "DUMMY_TASK_PRIORITY_INT",
    "KEEP_EMULATOR_OPEN_BOOL",
    "PROFILE_MAX_ACTIVE_TIME_ENABLED_BOOL",
    "PROFILE_MAX_ACTIVE_TIME_MINUTES_INT",
    "SKIP_TUTORIAL_ENABLED_BOOL",
    "TEST_GATHER_DEPLOY_PREEMPTION_BOOL",
)
_add(
    "training",
    "TRAIN_BOOL",
    "TRAIN_INFANTRY_BOOL",
    "TRAIN_LANCER_BOOL",
    "TRAIN_MARKSMAN_BOOL",
    "TRAIN_MINISTRY_APPOINTMENT_BOOL",
    "TRAIN_PRIORITIZE_PROMOTION_BOOL",
)


def is_hidden_key(key: str) -> bool:
    upper = str(key or "").strip().upper()
    if not upper:
        return True
    if upper in _LEGACY_KEYS or upper in _INTERNAL_KEYS:
        return True
    return upper.startswith("SHOP_NAVIGATION_")


def group_for_key(key: str) -> str | None:
    """Return a page id, ``""`` when the key should stay off the editor, or None."""
    upper = str(key or "").strip().upper()
    if is_hidden_key(upper):
        return ""
    return _PAGES_BY_KEY.get(upper)


def page_title(page_id: str) -> str | None:
    return _PAGE_TITLE.get(page_id)


def page_description(page_id: str) -> str:
    return _PAGE_DESC.get(page_id) or "Frostguard setting stored in the workspace database."


def page_sort_key(page_id: str, title: str) -> tuple[int, int | str]:
    order = _PAGE_INDEX.get(page_id)
    if order is None:
        return (1, title.lower())
    return (0, order)


# Frostguard's Config window. Every other key is a per-account workbench setting.
_BOT_GROUPS: tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "emulators",
        "Emulators",
        "Which emulator Frostguard launches, and where each one is installed.",
        (
            ("CURRENT_EMULATOR_STRING", "Active emulator"),
            ("LDPLAYER_PATH_STRING", "LDPlayer path"),
            ("MUMU_PATH_STRING", "MuMu Player path"),
            ("MEMU_PATH_STRING", "MEmu path"),
        ),
    ),
    (
        "instance",
        "Instance Settings",
        "How Frostguard opens, idles, and closes emulator instances.",
        (
            ("IDLE_BEHAVIOR_STRING", "Idle Behavior"),
            ("MAX_RUNNING_EMULATORS_INT", "Max Concurrent Instances"),
            ("MAX_IDLE_TIME_INT", "Max Idle Time (minutes)"),
            ("PROFILE_MAX_ACTIVE_TIME_ENABLED_BOOL", "Limit Profile Active Time"),
            ("PROFILE_MAX_ACTIVE_TIME_MINUTES_INT", "Profile active time (minutes)"),
            ("STOP_BEHAVIOR_STRING", "Stop Behavior"),
            ("AUTO_START_ENABLED_BOOL", "Auto start all Profiles after module load"),
            ("STOP_BEHAVIOR_TELEGRAM_STRING", "Stop Behavior Telegram"),
            ("AUTO_START_DELAY_MINUTES_INT", "Delay (minutes)"),
            ("AUTO_START_MODE_STRING", "Mode"),
        ),
    ),
    (
        "game",
        "Game Settings",
        "Which Whiteout Survival build Frostguard plays.",
        (("GAME_VERSION_STRING", "Game Version"),),
    ),
    (
        "analytics",
        "Analytics",
        "Anonymous usage data Frostguard can send.",
        (("ANALYTICS_ENABLED_BOOL", "Share anonymous usage data"),),
    ),
    (
        "telegram",
        "Telegram",
        "Frostguard's Telegram control switch. The bot token stays out of Sentinel.",
        (("TELEGRAM_BOT_ENABLED_BOOL", "Telegram bot enabled"),),
    ),
)

_WORKBENCH_PAGES = frozenset(
    {
        "alliance",
        "city",
        "dailies",
        "events",
        "experts",
        "gathering",
        "intel",
        "pets",
        "shops",
        "training",
    }
)

_BOT_LABELS = {
    key: label
    for _group_id, _title, _desc, fields in _BOT_GROUPS
    for key, label in fields
}


def is_workbench_page(page_id: str) -> bool:
    """Account workbench pages. Config, system, and testing stay off each account."""
    page = str(page_id or "").strip().lower()
    if not page:
        return False
    if page in _WORKBENCH_PAGES:
        return True
    if page in {group_id for group_id, _title, _desc, _fields in _BOT_GROUPS}:
        return False
    if page in {"system", "testing", "analytics"}:
        return False
    return True


def is_bot_setting(key: str) -> bool:
    return str(key or "").strip().upper() in _BOT_LABELS


def bot_field_label(key: str) -> str | None:
    return _BOT_LABELS.get(str(key or "").strip().upper())


def bot_setting_groups() -> list[dict[str, str | list[dict[str, str]]]]:
    groups: list[dict[str, str | list[dict[str, str]]]] = []
    for group_id, title, description, fields in _BOT_GROUPS:
        groups.append(
            {
                "id": group_id,
                "title": title,
                "description": description,
                "fields": [{"key": key, "label": label} for key, label in fields],
            }
        )
    return groups
