import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's class-name helper (A2) */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
