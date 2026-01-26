import { AsyncLocalStorage } from "async_hooks";
import { ObsEmitter } from "./obsClient.js";

export const als = new AsyncLocalStorage();
export const obs = new ObsEmitter();

export function getCtx() {
  return als.getStore() || null;
}
