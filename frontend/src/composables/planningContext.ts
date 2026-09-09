import { inject, provide, type InjectionKey } from 'vue'
import type { usePlanning } from './usePlanning'

/** A single usePlanning instance lives in App.vue and is shared by every view. */
export type PlanningInstance = ReturnType<typeof usePlanning>
const planningKey: InjectionKey<PlanningInstance> = Symbol('planning')

export function providePlanning(instance: PlanningInstance) {
  provide(planningKey, instance)
}

export function useSharedPlanning(): PlanningInstance {
  const instance = inject(planningKey)
  if (!instance) throw new Error('planning was not provided by the app shell')
  return instance
}
