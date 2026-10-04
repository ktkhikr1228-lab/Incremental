export type CardCount = { key: string; name: string; count: number; rarity?: string; description?: string };

export type Weapon = {
  power: number;
  rarity: string;
  originWave: number;
  multiplier?: number;
  fixed?: boolean;
};

export type Fight = {
  id?: string;
  elapsed?: number;
  hitCount?: number;
  supplemental?: number;
  reActionRate?: number;
  effectiveWeaponAtk?: number;
  hpSamples?: { time: number; remaining: number }[];
  wave: number;
  boss: boolean;
  enemyPower: number;
  hpPower: number;
  enemyHp: string;
  defensePower: number;
  armorBreakEnabled: boolean;
  dpsPower: number;
  dps: string;
  attackSpeed: number;
  critChance: number;
  critMultiplier: number;
  xpGain: number;
  baseAttack?: string;
  followRate?: number;
  timeLimit: number;
  timeToKill: number | null;
  willWin: boolean;
};

export type RunView = {
  attempt: number;
  kills: number;
  combatSeconds: number;
  totalCombatSeconds: number;
  xp: number;
  nextCardCost: number | null;
  cardCount: number;
  cards: CardCount[];
  weapon: Weapon | null;
  cardPoints: number;
};

export type Permanent = {
  dpVersion?: string;
  dpSpent?: number;
  dpUpgrades?: { key: string; label: string; level: number; cost: number; effect: string; unlocked: boolean; unlockWave: number }[];
  rerollUpgrade?: { bought: boolean; unlocked: boolean; cost: number };
  maxWave: number;
  bankedDp: number;
  totalDp: number;
  levels: { atk: number; attackSpeed: number; xp: number; total: number };
  nextDpCost: number;
  weaponMaterial: number;
  relicMaterial: number;
  weaponAcquisitions: number;
  weaponGenerations: number;
  relicDrops: number;
  relicGenerations: number;
  relicTypes: number;
  relicDuplicates: number;
  relicQuality: number;
  relicUnlocked: boolean;
};

export type CardOption = {
  key: string;
  name: string;
  rarity: string;
  description: string;
  tags: string[];
  eligible: boolean;
  score: number;
  immediateMultiplier: number | null;
  afterDpsPower: number;
  nextTtk: number | null;
  nextTimeLimit: number;
};

export type SessionState = {
  nonBlocking?: boolean;
  cardDrafts?: number;
  pendingEquipmentList?: EquipmentItem[];
  status: 'idle' | 'combat' | 'card' | 'weapon' | 'equipment' | 'death' | 'complete';
  equipmentMode?: boolean;
  equipmentDismantleMultiplier?: number;
  candidateNotice?: string;
  equipment?: EquipmentInventory;
  pendingEquipment?: EquipmentItem | null;
  profile?: string;
  profileName?: string;
  seed?: number;
  targetWave?: number;
  fight?: Fight | null;
  player?: Partial<Fight>;
  run?: RunView;
  permanent?: Permanent;
  options?: CardOption[];
  starterGuarantee?: boolean;
  forcedRarity?: string | null;
  rerollsLeft?: number;
  recommendedCard?: string | null;
  pendingWeapon?: Weapon | null;
  weaponContext?: string | null;
  death?: {
    failureWave: number;
    reached: number;
    gainedDp: number;
    runCombatSeconds: number;
  } | null;
  canForgeWeapon?: boolean;
  forgeWeaponCost?: number;
  canForgeRelic?: boolean;
  forgeRelicCost?: number;
  logs?: string[];
  notice?: string;
};

export type EquipmentItem = {
  uid: string; kind: 'weapon' | 'relic'; name: string; rarity: string;
  origin_wave: number; base_atk: number; quality: number;
  affixes: Record<string, number>; unique_key: string | null;
  enhancement: number; enhancement_spent: number; duplicate_levels: number;
};
export type EquipmentInventory = {
  items: Record<string, EquipmentItem>; weapon_slot: string | null;
  relic_slots: (string | null)[]; storage_capacity: Record<string, number>;
  materials: Record<string, number>;
};

export type ActionHandler = (type: string, extra?: Record<string, unknown>) => void;

export function formatNumber(value: number | undefined, digits = 2) {
  if (value === undefined) return '—';
  return value.toLocaleString('ja-JP', { maximumFractionDigits: digits });
}

export function formatTime(value: number | undefined) {
  if (value === undefined) return '—';
  if (value < 60) return `${value.toFixed(2)}秒`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = Math.round(value % 60);
  return hours ? `${hours}時間${minutes}分` : `${minutes}分${seconds}秒`;
}
