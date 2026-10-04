import { dateValue, localDate } from "./meetings"

export function formatHour(hour: number): string {
  const totalMinutes = Math.round(hour * 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours % 12 || 12}${
    minutes ? `:${String(minutes).padStart(2, "0")}` : ""
  } ${hours < 12 ? "AM" : "PM"}`
}
export function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value]
}
export function addDays(date: string, days: number): string {
  const value = localDate(date)
  value.setDate(value.getDate() + days)
  return dateValue(value)
}
export function weekOf(date: string): string {
  const value = localDate(date)
  return addDays(date, -((value.getDay() + 6) % 7))
}
