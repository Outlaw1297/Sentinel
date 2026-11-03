"""Frostguard's per-account sidebar, taken from the operator panel.

ConfigCategory is not the page list. City Events, Extra City Events, Rally,
Shop, and the alliance pages are separate tabs.
"""

from __future__ import annotations

from typing import Any

# id, title, description, header toggle key or "".
_PAGES: tuple[tuple[str, str, str, str], ...] = (
    ("dummy-task", "Dummy Task", "Runs until it finds go.png. Checks every 5 seconds and waits 60 minutes when it finds one.", "DUMMY_TASK_ENABLED_BOOL"),
    ("city-upgrades", "City Upgrades", "Configure automated building upgrades safely.", ""),
    ("city-events", "City Events", "Configure automated tasks for internal city events.", ""),
    ("extra-city-events", "Extra City Events", "Arena and the other daily city tasks.", ""),
    ("rally", "Rally", "Polar Terror and manual rally join.", ""),
    ("shops", "Shop", "Nomadic Merchant, Bank, and Mystery Shop.", ""),
    ("gather", "Gather", "Send marches for selected resources.", "GATHER_TASK_BOOL"),
    ("intel", "Intel", "Choose the intel types to process.", "INTEL_BOOL"),
    ("alliance", "Alliance", "Daily claims, autojoin, and help requests.", ""),
    ("alliance-championship", "Alliance Championship", "Deployment position, flag, and troop mix.", "ALLIANCE_CHAMPIONSHIP_BOOL"),
    ("alliance-shop", "Alliance Shop", "Coin thresholds and purchase order.", "ALLIANCE_SHOP_ENABLED_BOOL"),
    ("alliance-mobilization", "Alliance Mobilization", "Mission types and point thresholds.", "ALLIANCE_MOBILIZATION_BOOL"),
    ("bear-trap", "Bear Trap", "Timers, protection, and rally behavior.", ""),
    ("beast-hunting", "Beast Hunting", "Hunts beasts with the marches you allow. Stamina below the reserve stays for Intel and Rally.", "BEAST_HUNTING_ENABLED_BOOL"),
    ("fishing", "Fishing Tournament", "Fishing minigame and the test hook loop.", "FISHING_MINIGAME_ENABLED_BOOL"),
    ("training", "Training", "Automate training troops.", "TRAIN_BOOL"),
    ("research", "Research", "Automate research in your city.", "RESEARCH_ENABLED_BOOL"),
    ("pets", "Pets", "Pet skills and treasures.", ""),
    ("events", "Events", "Journey of Light, mercenaries, hero missions, and trucks.", ""),
    ("experts", "Experts", "Expert skills and troop assignments.", ""),
    ("chief-orders", "Chief Orders", "Chief orders to complete on a timer.", ""),
)

_PAGE_INDEX = {page_id: index for index, (page_id, _title, _desc, _toggle) in enumerate(_PAGES)}
_PAGE_TITLE = {page_id: title for page_id, title, _desc, _toggle in _PAGES}
_PAGE_DESC = {page_id: desc for page_id, _title, desc, _toggle in _PAGES}
_PAGE_TOGGLE = {page_id: toggle for page_id, _title, _desc, toggle in _PAGES if toggle}

# section title, then (key, label, beside_key or "").
_LAYOUT: dict[str, tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]] = {
    "dummy-task": (
        ("", (("DUMMY_TASK_PRIORITY_INT", "Priority", ""),)),
    ),
    "city-upgrades": (
        (
            "",
            (
                ("CITY_UPGRADE_FURNACE_BOOL", "Upgrade Furnace", ""),
                ("CITY_UPGRADE_RESERVE_PRODUCTION_BOOL", "Reserve training/research for required upgrades", ""),
                ("CITY_UPGRADE_PRIORITISE_FURNACE_BOOL", "Prioritise Furnace", ""),
                ("CITY_ACCEPT_NEW_SURVIVORS_BOOL", "Accept new survivors", ""),
                ("CITY_ACCEPT_NEW_SURVIVORS_OFFSET_INT", "Offset Time", "CITY_ACCEPT_NEW_SURVIVORS_BOOL"),
                ("CITY_UPGRADE_CONSTRUCTION_LOCK_STRING", "Construction lock", ""),
            ),
        ),
    ),
    "city-events": (
        (
            "",
            (
                ("DAILY_MISSION_BOOL", "Claim daily missions", ""),
                ("DAILY_MISSION_OFFSET_INT", "Offset", "DAILY_MISSION_BOOL"),
                ("DAILY_MISSION_AUTO_SCHEDULE_BOOL", "Auto schedule daily mission claim", ""),
                ("BOOL_DO_EXPLORATION", "Do Exploration", ""),
                ("DO_EXPLORATION_QUICK_DEPLOY_BOOL", "Use Quick Deploy before each fight", ""),
                ("BOOL_EXPLORATION_CHEST", "Claim exploration chest", ""),
                ("INT_EXPLORATION_CHEST_OFFSET", "Offset", "BOOL_EXPLORATION_CHEST"),
                ("MAIL_REWARDS_BOOL", "Claim mail rewards", ""),
                ("MAIL_REWARDS_OFFSET_INT", "Offset", "MAIL_REWARDS_BOOL"),
                ("LIFE_ESSENCE_BOOL", "Claim life essence", ""),
                ("LIFE_ESSENCE_BUY_WEEKLY_SCROLL_BOOL", "Buy weekly scroll", ""),
                ("LIFE_ESSENCE_OFFSET_INT", "Offset", "LIFE_ESSENCE_BOOL"),
                ("BOOL_CRYSTAL_LAB_FC", "Claim crystal lab FC", ""),
                ("BOOL_CRYSTAL_LAB_DAILY_DISCOUNTED_RFC", "Claim daily 50% RFC", ""),
                ("INT_WEEKLY_RFC", "Monday refinement", "BOOL_CRYSTAL_LAB_DAILY_DISCOUNTED_RFC"),
                ("WAR_ACADEMY_TASK_BOOL", "Claim war academy crystal shards", ""),
            ),
        ),
    ),
    "extra-city-events": (
        (
            "Arena",
            (
                ("ARENA_TASK_BOOL", "Enable arena", ""),
                ("ARENA_TASK_ACTIVATION_TIME_STRING", "Activation time (UTC)", ""),
                ("ARENA_TASK_EXTRA_ATTEMPTS_INT", "Extra attempts", ""),
                ("ARENA_TASK_REFRESH_WITH_GEMS_BOOL", "Allow paid list refreshes", ""),
                ("ARENA_TASK_ATTACK_QUICK_DEPLOY_BOOL", "Use Quick Deploy for attacks", ""),
                ("ARENA_TASK_ALLIANCE_POLICY_STRING", "Alliance filter", ""),
                ("ARENA_TASK_SERVER_POLICY_STRING", "Server policy", ""),
            ),
        ),
        (
            "Other Tasks",
            (
                ("BOOL_VIP_POINTS", "Claim daily VIP rewards", ""),
                ("STOREHOUSE_CHEST_BOOL", "Claim storehouse chests + stamina", ""),
                ("STOREHOUSE_STAMINA_CLAIM_TIME_STRING", "Stamina claim time", "STOREHOUSE_CHEST_BOOL"),
                ("BOOL_HERO_RECRUITMENT", "Open recruitment hero chests", ""),
                ("DAILY_LABYRINTH_BOOL", "Complete daily labyrinth", ""),
                ("VIP_MONTHLY_BUY_BOOL", "Buy monthly VIP (10k gems)", ""),
                ("TUNDRA_TREK_SUPPLIES_BOOL", "Claim Trek Supplies", ""),
                ("TUNDRA_TREK_AUTOMATION_BOOL", "Tundra Trek Automation", ""),
            ),
        ),
    ),
    "rally": (
        (
            "Polar Terror",
            (
                ("POLAR_TERROR_ENABLED_BOOL", "Enable Polar Terror", ""),
                ("POLAR_TERROR_HIGHEST_LEVEL_BOOL", "Highest level", ""),
                ("POLAR_TERROR_LEVEL_INT", "Level", ""),
                ("POLAR_TERROR_MARCHES_INT", "Marches", ""),
                ("POLAR_TERROR_MODE_STRING", "Mode", ""),
                ("POLAR_TERROR_USE_STAMINA_ITEMS_BOOL", "Use stamina items", ""),
                ("POLAR_TERROR_STAMINA_ITEM_RESERVE_INT", "Stamina item reserve", ""),
                ("POLAR_TERROR_MARCH_1_FLAG_STRING", "March 1 flag", ""),
                ("POLAR_TERROR_MARCH_2_FLAG_STRING", "March 2 flag", ""),
                ("POLAR_TERROR_MARCH_3_FLAG_STRING", "March 3 flag", ""),
                ("POLAR_TERROR_MARCH_4_FLAG_STRING", "March 4 flag", ""),
                ("POLAR_TERROR_MARCH_5_FLAG_STRING", "March 5 flag", ""),
                ("POLAR_TERROR_MARCH_6_FLAG_STRING", "March 6 flag", ""),
            ),
        ),
        (
            "Manual Rally Join",
            (
                ("RALLY_ENABLED_BOOL", "Manual Rally Join (Preemptive)", ""),
                ("RALLY_MODE_STRING", "Operation Mode", ""),
                ("RALLY_MARCHES_INT", "Number of Marches", ""),
                ("RALLY_TARGET_STRING", "Target", ""),
                ("RALLY_MARCH_1_FLAG_STRING", "March 1 flag", ""),
                ("RALLY_MARCH_2_FLAG_STRING", "March 2 flag", ""),
                ("RALLY_MARCH_3_FLAG_STRING", "March 3 flag", ""),
                ("RALLY_MARCH_4_FLAG_STRING", "March 4 flag", ""),
                ("RALLY_MARCH_5_FLAG_STRING", "March 5 flag", ""),
                ("RALLY_MARCH_6_FLAG_STRING", "March 6 flag", ""),
            ),
        ),
    ),
    "shops": (
        (
            "Nomadic Merchant",
            (
                ("BOOL_NOMADIC_MERCHANT", "Buy resources", ""),
                ("BOOL_NOMADIC_MERCHANT_VIP_POINTS", "Buy VIP points", ""),
            ),
        ),
        (
            "Bank",
            (
                ("BOOL_BANK", "Enable Bank", ""),
                ("INT_BANK_DELAY", "Period", ""),
            ),
        ),
        (
            "Mystery Shop",
            (
                ("BOOL_MYSTERY_SHOP", "Enable Mystery Shop", ""),
                ("BOOL_MYSTERY_SHOP_250_HERO_WIDGET", "Buy 50% discounted hero gear (250 badges)", ""),
                ("BOOL_MYSTERY_SHOP_250_SHARD", "Buy 50% discounted shards (250 badges)", ""),
            ),
        ),
    ),
    "gather": (
        (
            "",
            (
                ("GATHER_MEAT_BOOL", "Meat", ""),
                ("GATHER_MEAT_LEVEL_INT", "Level", "GATHER_MEAT_BOOL"),
                ("GATHER_WOOD_BOOL", "Wood", ""),
                ("GATHER_WOOD_LEVEL_INT", "Level", "GATHER_WOOD_BOOL"),
                ("GATHER_COAL_BOOL", "Coal", ""),
                ("GATHER_COAL_LEVEL_INT", "Level", "GATHER_COAL_BOOL"),
                ("GATHER_IRON_BOOL", "Iron", ""),
                ("GATHER_IRON_LEVEL_INT", "Level", "GATHER_IRON_BOOL"),
            ),
        ),
        (
            "March Settings",
            (
                ("GATHER_ACTIVE_MARCH_QUEUE_INT", "Active queues", ""),
                ("GATHER_ROTATION_POOL", "Rotation pool", ""),
                ("GATHER_ONLY_FULL_RESOURCES_BOOL", "Only search for full resources", ""),
                ("GATHER_DOWNGRADE_LEVEL_BOOL", "Downgrade level if no node is found", ""),
                ("GATHER_REMOVE_HEROS_BOOL", "Remove 2nd and 3rd hero from march", ""),
                ("GATHER_NO_HERO_FALLBACK_BOOL", "Send without heroes if Gather hero is unavailable", ""),
            ),
        ),
        (
            "Boosts",
            (
                ("GATHER_SPEED_BOOL", "Gather Speed Boost", ""),
                ("GATHER_SPEED_BOOST_TYPE_STRING", "Boost", "GATHER_SPEED_BOOL"),
                ("TEST_GATHER_DEPLOY_PREEMPTION_BOOL", "TEST: Trigger Preemption on Gather Deploy", ""),
            ),
        ),
    ),
    "intel": (
        (
            "Intel Categories",
            (
                ("INTEL_FC_ERA_BOOL", "Fire Crystal Era", ""),
                ("INTEL_FIRE_BEAST_BOOL", "Fire Beast", ""),
                ("INTEL_BEASTS_BOOL", "Beast", ""),
                ("INTEL_CAMP_BOOL", "Survivors", ""),
                ("INTEL_EXPLORATION_BOOL", "Journey", ""),
                ("INTEL_BEASTS_EVENT_BOOL", "Beast event", ""),
            ),
        ),
        (
            "Processing",
            (
                ("INTEL_SMART_PROCESSING_BOOL", "Use Smart Intel Processing", ""),
                ("INTEL_RECALL_GATHER_TROOPS_BOOL", "Recall Gather Troops", ""),
                ("INTEL_USE_FLAG_BOOL", "Use Beast flag", ""),
                ("INTEL_BEASTS_FLAG_INT", "Beast flag", "INTEL_USE_FLAG_BOOL"),
            ),
        ),
    ),
    "alliance": (
        (
            "Daily Claims",
            (
                ("ALLIANCE_TECH_BOOL", "Tech contribution", ""),
                ("ALLIANCE_TECH_OFFSET_INT", "Offset", "ALLIANCE_TECH_BOOL"),
                ("ALLIANCE_CHESTS_BOOL", "Claim chests", ""),
                ("ALLIANCE_CHESTS_OFFSET_INT", "Offset", "ALLIANCE_CHESTS_BOOL"),
                ("ALLIANCE_HONOR_CHEST_BOOL", "Claim honor chest", ""),
                ("ALLIANCE_TRIUMPH_BOOL", "Claim Triumph", ""),
                ("ALLIANCE_TRIUMPH_OFFSET_INT", "Offset", "ALLIANCE_TRIUMPH_BOOL"),
                ("ALLIANCE_LIFE_ESSENCE_BOOL", "Claim allies essence", ""),
                ("ALLIANCE_LIFE_ESSENCE_OFFSET_INT", "Fail offset", "ALLIANCE_LIFE_ESSENCE_BOOL"),
            ),
        ),
        (
            "Rally AutoJoin",
            (
                ("ALLIANCE_AUTOJOIN_BOOL", "Enable Autojoin", ""),
                ("ALLIANCE_AUTOJOIN_QUEUES_INT", "Queues", ""),
                ("ALLIANCE_HELP_BOOL", "Help alliance requests", ""),
            ),
        ),
        (
            "Troop Source",
            (
                ("ALLIANCE_AUTOJOIN_USE_ALL_TROOPS_BOOL", "All Troops", ""),
                ("ALLIANCE_AUTOJOIN_USE_PREDEFINED_FORMATION_BOOL", "Use Formation", ""),
            ),
        ),
    ),
    "alliance-championship": (
        (
            "",
            (
                ("ALLIANCE_CHAMPIONSHIP_POSITION_STRING", "Position", ""),
                ("ALLIANCE_CHAMPIONSHIP_OVERRIDE_DEPLOY_BOOL", "Override Current Deployment", ""),
                ("ALLIANCE_CHAMPIONSHIP_FLAG_STRING", "Flag Selection", ""),
                ("ALLIANCE_CHAMPIONSHIP_INFANTRY_PERCENTAGE_INT", "Infantry %", ""),
                ("ALLIANCE_CHAMPIONSHIP_LANCERS_PERCENTAGE_INT", "Lancers %", ""),
                ("ALLIANCE_CHAMPIONSHIP_MARKSMANS_PERCENTAGE_INT", "Marksmen %", ""),
            ),
        ),
    ),
    "alliance-shop": (
        (
            "Configuration",
            (
                ("ALLIANCE_SHOP_MIN_COINS_TO_ACTIVATE_INT", "Min Coins to Activate", ""),
                ("ALLIANCE_SHOP_MIN_COINS_INT", "Min Coins", ""),
                ("ALLIANCE_SHOP_MIN_PERCENTAGE_INT", "Min Percentage", ""),
            ),
        ),
        (
            "Purchase Priorities",
            (("ALLIANCE_SHOP_PRIORITIES_STRING", "Purchase Priorities", ""),),
        ),
    ),
    "alliance-mobilization": (
        (
            "Mission Types",
            (
                ("ALLIANCE_MOBILIZATION_GATHER_RESOURCES_BOOL", "Gathering", ""),
                ("ALLIANCE_MOBILIZATION_DEFEAT_BEASTS_BOOL", "Beast Slaying", ""),
                ("ALLIANCE_MOBILIZATION_TRAIN_TROOPS_BOOL", "Training", ""),
                ("ALLIANCE_MOBILIZATION_BUILD_SPEEDUPS_BOOL", "Build Speedups", ""),
                ("ALLIANCE_MOBILIZATION_TRAINING_SPEEDUPS_BOOL", "Training Speedups", ""),
                ("ALLIANCE_MOBILIZATION_USE_SPEEDUPS_BOOL", "Use Speedups", ""),
                ("ALLIANCE_MOBILIZATION_USE_GEMS_BOOL", "Use Gems", ""),
                ("ALLIANCE_MOBILIZATION_BUY_PACKAGE_BOOL", "Buy Package", ""),
                ("ALLIANCE_MOBILIZATION_CHIEF_GEAR_CHARM_BOOL", "Chief Gear Charm", ""),
                ("ALLIANCE_MOBILIZATION_CHIEF_GEAR_SCORE_BOOL", "Chief Gear Score", ""),
                ("ALLIANCE_MOBILIZATION_HERO_GEAR_STONE_BOOL", "Hero Gear Stone", ""),
                ("ALLIANCE_MOBILIZATION_MYTHIC_SHARD_BOOL", "Mythic Shard", ""),
                ("ALLIANCE_MOBILIZATION_FIRE_CRYSTAL_BOOL", "Fire Crystal", ""),
                ("ALLIANCE_MOBILIZATION_RALLY_BOOL", "Rally", ""),
                ("ALLIANCE_MOBILIZATION_AUTO_ACCEPT_BOOL", "Auto Accept", ""),
                ("ALLIANCE_MOBILIZATION_USE_GEMS_FOR_ACCEPT_BOOL", "Use Gems for Accept", ""),
            ),
        ),
        (
            "Configuration",
            (
                ("ALLIANCE_MOBILIZATION_REWARDS_PERCENTAGE_STRING", "Rewards %", ""),
                ("ALLIANCE_MOBILIZATION_MINIMUM_POINTS_200_INT", "Min Points (200)", ""),
                ("ALLIANCE_MOBILIZATION_MINIMUM_POINTS_120_INT", "Min Points (120)", ""),
            ),
        ),
    ),
    "bear-trap": (
        (
            "Timers",
            (
                ("BEAR_TRAP_PREPARATION_TIME_INT", "Preparation and protection lead time", ""),
                ("BEAR_TRAP_NUMBER_INT", "Bear Trap number", ""),
                ("BEAR_TRAP_SCHEDULE_DATETIME_STRING", "Bear Trap 1 start (UTC)", ""),
                ("BEAR_TRAP_TIMER_2_SCHEDULE_DATETIME_STRING", "Bear Trap 2 start (UTC)", ""),
                ("BEAR_TRAP_TIMER_1_ENABLED_BOOL", "Bear Trap 1 timer", ""),
                ("BEAR_TRAP_TIMER_2_ENABLED_BOOL", "Bear Trap 2 timer", ""),
                ("BEAR_TRAP_TIMER_1_BLOCK_RALLIES_BOOL", "Bear Trap 1 block rallies", ""),
                ("BEAR_TRAP_TIMER_2_BLOCK_RALLIES_BOOL", "Bear Trap 2 block rallies", ""),
                ("BEAR_TRAP_TIMER_1_PAUSE_ALL_TASKS_BOOL", "Bear Trap 1 pause tasks", ""),
                ("BEAR_TRAP_TIMER_2_PAUSE_ALL_TASKS_BOOL", "Bear Trap 2 pause tasks", ""),
            ),
        ),
        (
            "Automation",
            (
                ("BEAR_TRAP_EVENT_BOOL", "Enable Bear Trap automation", ""),
                ("BEAR_TRAP_JOIN_RALLY_BOOL", "Join rally", ""),
                ("BEAR_TRAP_JOIN_FLAG_INT", "Join flag", ""),
                ("BEAR_TRAP_ICON_PARTICIPATION_FALLBACK_BOOL", "Icon participation fallback", ""),
            ),
        ),
        (
            "Preparation",
            (
                ("BEAR_TRAP_ACTIVE_PETS_BOOL", "Activate pets before Bear Trap", ""),
                ("BEAR_TRAP_RECALL_TROOPS_BOOL", "Recall gathering troops before Bear Trap", ""),
            ),
        ),
        (
            "Rally Behavior",
            (
                ("BEAR_TRAP_CALL_RALLY_BOOL", "Call Own Rally", ""),
                ("BEAR_TRAP_RALLY_FLAG_INT", "Rally Flag", ""),
            ),
        ),
    ),
    "beast-hunting": (
        (
            "",
            (
                ("BEAST_HUNTING_MARCHES_INT", "Active Marches", ""),
                ("BEAST_HUNTING_LEVEL_INT", "Beast Level", ""),
                ("STAMINA_RESERVE_INT", "Stamina Reserve", ""),
            ),
        ),
    ),
    "fishing": (
        (
            "Fishing Minigame",
            (
                ("FISHING_MAX_CASTS_INT", "Max casts", ""),
                ("FISHING_TARGET_CATCHES_INT", "Target catches", ""),
                ("FISHING_MAX_RESTARTS_INT", "Max restarts", ""),
                ("FISHING_USE_LANTERN_BOOL", "Use lantern", ""),
                ("FISHING_USE_STABILIZER_BOOL", "Use stabilizer", ""),
            ),
        ),
        (
            "Test Hook Loop",
            (("TEST_HOOK_LOOP_ENABLED_BOOL", "Enable Test Hook Loop", ""),),
        ),
    ),
    "training": (
        (
            "Troop Selection",
            (
                ("TRAIN_INFANTRY_BOOL", "Train Infantry", ""),
                ("TRAIN_MARKSMAN_BOOL", "Train Marksmen", ""),
                ("TRAIN_LANCER_BOOL", "Train Lancers", ""),
                ("TRAIN_PRIORITIZE_PROMOTION_BOOL", "Prioritize Troop Promotion", ""),
                ("TRAIN_MINISTRY_APPOINTMENT_BOOL", "Appoint Minister of Education", ""),
            ),
        ),
    ),
    "research": (
        (
            "",
            (
                ("RESEARCH_PRIORITIES_STRING", "Research Priorities", ""),
                ("RESEARCH_BATTLE_BOOL", "Battle", ""),
                ("RESEARCH_GROWTH_BOOL", "Growth", ""),
                ("RESEARCH_ECONOMY_BOOL", "Economy", ""),
            ),
        ),
    ),
    "pets": (
        (
            "Pet Automation",
            (
                ("PET_SKILLS_BOOL", "Enable Pet Management", ""),
                ("ALLIANCE_PET_TREASURE_BOOL", "Alliance Treasure", ""),
                ("PET_PERSONAL_TREASURE_BOOL", "Personal Treasure", ""),
            ),
        ),
        (
            "Skill Configuration",
            (
                ("PET_SKILL_FOOD_BOOL", "Food Skill", ""),
                ("PET_SKILL_GATHERING_BOOL", "Gathering Skill", ""),
                ("PET_SKILL_STAMINA_BOOL", "Stamina Skill", ""),
                ("PET_SKILL_TREASURE_BOOL", "Treasure Skill", ""),
                ("PET_SKILL_GATHERING_RESOURCE_STRING", "Gathering Resource", ""),
            ),
        ),
    ),
    "events": (
        (
            "Journey of Light",
            (("JOURNEY_OF_LIGHT_BOOL", "Journey of Light", ""),),
        ),
        (
            "Mercenary Event",
            (
                ("MERCENARY_EVENT_BOOL", "Mercenary Event", ""),
                ("MERCENARY_FLAG_INT", "Flag Selection", ""),
            ),
        ),
        (
            "Hero's Mission Event",
            (
                ("HERO_MISSION_EVENT_BOOL", "Hero's Mission Event", ""),
                ("HERO_MISSION_FLAG_INT", "Flag Selection", ""),
            ),
        ),
        (
            "Myriad Bazaar",
            (("MYRIAD_BAZAAR_EVENT_BOOL", "Myriad Bazaar", ""),),
        ),
        (
            "Tundra Truck Event",
            (
                ("TUNDRA_TRUCK_EVENT_BOOL", "Tundra Truck Event", ""),
                ("TUNDRA_TRUCK_USE_GEMS_BOOL", "Use gems for refresh", ""),
                ("TUNDRA_TRUCK_ACTIVATION_TIME_BOOL", "Use activation time", ""),
                ("TUNDRA_TRUCK_ACTIVATION_TIME_STRING", "Activation time", "TUNDRA_TRUCK_ACTIVATION_TIME_BOOL"),
                ("TUNDRA_TRUCK_SSR_BOOL", "Go only for SSR trucks", ""),
            ),
        ),
    ),
    "experts": (
        (
            "",
            (
                ("EXPERT_AGNES_INTEL_BOOL", "Claim Intel (Agnes)", ""),
                ("EXPERT_ROMULUS_TAG_BOOL", "Claim Loyalty Tag (Romulus)", ""),
                ("EXPERT_ROMULUS_TROOPS_BOOL", "Claim Troops (Romulus)", ""),
                ("EXPERT_ROMULUS_TROOPS_TYPE_STRING", "Troop Type", ""),
                ("EXPERT_SKILL_TRAINING_ENABLED_BOOL", "Enable Expert Skill Training", ""),
                ("EXPERT_SKILL_TRAINING_PRIORITIES_STRING", "Expert Skill Training Priorities", ""),
            ),
        ),
    ),
    "chief-orders": (
        (
            "",
            (
                ("BOOL_CHIEF_ORDER_RUSH_JOB", "Rush Job (every 24h)", ""),
                ("BOOL_CHIEF_ORDER_URGENT_MOBILISATION", "Urgent Mobilisation (every 8h)", ""),
                ("BOOL_CHIEF_ORDER_PRODUCTIVITY_DAY", "Productivity Day (every 12h)", ""),
            ),
        ),
    ),
}

_SELECTS: dict[str, list[str]] = {
    "ARENA_TASK_SERVER_POLICY_STRING": ["Never attack profile server", "Any server"],
    "ALLIANCE_AUTOJOIN_QUEUES_INT": ["1", "2", "3", "4", "5", "6"],
    "GATHER_ACTIVE_MARCH_QUEUE_INT": ["1", "2", "3", "4", "5", "6"],
    "EXPERT_ROMULUS_TROOPS_TYPE_STRING": ["Infantry", "Lancer", "Marksman"],
    "PET_SKILL_GATHERING_RESOURCE_STRING": ["MEAT", "WOOD", "COAL", "IRON"],
    "BEAST_HUNTING_MARCHES_INT": ["1", "2", "3", "4", "5", "6"],
    "RALLY_MARCHES_INT": ["1", "2", "3", "4", "5", "6"],
    "POLAR_TERROR_MARCHES_INT": ["1", "2", "3", "4", "5", "6"],
}

# Keys that exist in the database but are not drawn on a screenshot still
# belong on the same sidebar page as the rest of that task.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("ALLIANCE_CHAMPIONSHIP_", "alliance-championship"),
    ("ALLIANCE_SHOP_", "alliance-shop"),
    ("ALLIANCE_MOBILIZATION_", "alliance-mobilization"),
    ("ALLIANCE_", "alliance"),
    ("BEAR_TRAP_", "bear-trap"),
    ("BEAST_HUNTING_", "beast-hunting"),
    ("FISHING_", "fishing"),
    ("POLAR_TERROR_", "rally"),
    ("RALLY_", "rally"),
    ("CITY_", "city-upgrades"),
    ("GATHER_", "gather"),
    ("INTEL_", "intel"),
    ("PET_", "pets"),
    ("TRAIN_", "training"),
    ("RESEARCH_", "research"),
    ("EXPERT_", "experts"),
    ("TUNDRA_TRUCK_", "events"),
    ("TUNDRA_TREK_", "extra-city-events"),
    ("ARENA_", "extra-city-events"),
    ("DUMMY_", "dummy-task"),
    ("BOOL_CHIEF_ORDER_", "chief-orders"),
    ("DAILY_", "city-events"),
    ("MAIL_", "city-events"),
    ("LIFE_ESSENCE_", "city-events"),
    ("STOREHOUSE_", "extra-city-events"),
    ("VIP_", "extra-city-events"),
    ("WAR_ACADEMY_", "city-events"),
    ("TEST_HOOK_", "fishing"),
    ("TEST_GATHER_", "gather"),
    ("STAMINA_RESERVE_", "beast-hunting"),
    ("HERO_MISSION_", "events"),
    ("JOURNEY_OF_LIGHT_", "events"),
    ("MERCENARY_", "events"),
    ("MYRIAD_", "events"),
)

_FIELD_META: dict[str, dict[str, Any]] = {}
_KEY_PAGE: dict[str, str] = {}
for _page_id, _sections in _LAYOUT.items():
    for _section, _fields in _sections:
        for _key, _label, _beside in _fields:
            _KEY_PAGE[_key] = _page_id
            _FIELD_META[_key] = {
                "label": _label,
                "section": _section,
                "beside": _beside,
                "options": list(_SELECTS.get(_key, [])),
            }
for _page_id, _toggle in _PAGE_TOGGLE.items():
    _KEY_PAGE.setdefault(_toggle, _page_id)


def account_page_for_key(key: str) -> str | None:
    upper = str(key or "").strip().upper()
    if not upper:
        return None
    found = _KEY_PAGE.get(upper)
    if found:
        return found
    for prefix, page_id in _PREFIXES:
        if upper.startswith(prefix):
            return page_id
    return None


def account_page_title(page_id: str) -> str | None:
    return _PAGE_TITLE.get(page_id)


def account_page_description(page_id: str) -> str:
    return _PAGE_DESC.get(page_id, "")


def account_page_toggle(page_id: str) -> str:
    return _PAGE_TOGGLE.get(page_id, "")


def account_page_sort(page_id: str) -> tuple[int, int | str]:
    order = _PAGE_INDEX.get(page_id)
    if order is None:
        return (1, page_id)
    return (0, order)


def account_field_meta(key: str) -> dict[str, Any] | None:
    return _FIELD_META.get(str(key or "").strip().upper())


def account_sections(page_id: str) -> tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]:
    return _LAYOUT.get(page_id, ())
