import type { Category, EvidenceTier, RuleStatus } from "@/lib/api/types";

type Pair = [string, string];

export const CATEGORY_LABEL: Record<Category, Pair> = {
  rent_increase_limits: ["Rent increases", "Aumentos de renta"],
  just_cause_eviction: ["Eviction protections", "Protección contra desalojos"],
  security_deposits: ["Security deposits", "Depósitos de seguridad"],
  application_screening_fees: ["Application fees", "Cuotas de solicitud"],
  screening_restrictions: ["Tenant screening", "Evaluación de inquilinos"],
  algorithmic_rent_setting: ["Rent-setting software", "Software para fijar rentas"],
};

export const STATUS_LABEL: Record<RuleStatus, Pair> = {
  in_force: ["In force", "Vigente"],
  not_yet_effective: ["Not yet effective", "Aún no vigente"],
  pending: ["Pending", "Pendiente"],
  failed: ["Failed", "Fallida"],
};

export const TIER_LABEL: Record<EvidenceTier, Pair> = {
  A: ["Official text", "Texto oficial"],
  B: ["Official guidance", "Guía oficial"],
  C: ["Text not supplied", "Texto no proporcionado"],
  C1: ["Single source, unconfirmed", "Fuente única, sin confirmar"],
};
