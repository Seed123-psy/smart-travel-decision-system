import { ref } from 'vue'
import type { TripDetail } from '../types/planning'

/** The trip the visitor is currently looking at (detail page or the one just generated). */
export const currentTrip = ref<TripDetail | null>(null)

export function setCurrentTrip(trip: TripDetail | null) {
  currentTrip.value = trip
}
