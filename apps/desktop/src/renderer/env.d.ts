import type { GarudaApi } from '../preload/index'

declare global {
  interface Window {
    garuda: GarudaApi
  }
}

export {}
