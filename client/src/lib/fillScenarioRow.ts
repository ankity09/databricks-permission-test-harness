import type { ActionDescriptor, NodeType, ScenarioItem } from '../types'
import { nodeTypeToLevel, selectActionForNode } from './selectAction'

/**
 * Fill scenario rows intelligently when a catalog node is picked.
 * Returns: { newItems, hint } where hint is shown if no fillable/appendable row exists.
 */
export function fillScenarioRowWithNode(
  currentItems: ScenarioItem[],
  pickedPath: string,
  pickedType: NodeType,
  grantableActions: ActionDescriptor[],
): {
  newItems: ScenarioItem[]
  hint: string | null
} {
  const pickedLevel = nodeTypeToLevel(pickedType)
  if (!pickedLevel) {
    return { newItems: currentItems, hint: null }
  }

  const bestAction = selectActionForNode(pickedType, grantableActions)

  // Check if the picked (action, securable) pair already exists exactly
  if (bestAction) {
    const existingIdx = currentItems.findIndex(
      (it) => it.action_id === bestAction.id && it.securable === pickedPath,
    )
    if (existingIdx >= 0) {
      // De-duplicate: return same items (caller will highlight the existing row)
      return { newItems: currentItems, hint: null }
    }
  }

  // Find the first row that is fillable:
  // - securable is empty OR
  // - securable contains a {placeholder}
  // Prefer a row whose current action's securable_level matches the picked node's level
  let fillIdx = -1
  let fillIdxGeneral = -1

  for (let i = 0; i < currentItems.length; i++) {
    const it = currentItems[i]
    const isEmpty = !it.securable.trim()
    const isPlaceholder = it.securable.includes('{')
    if (!isEmpty && !isPlaceholder) continue

    // This row is fillable
    if (fillIdxGeneral === -1) fillIdxGeneral = i

    // Check if current action's securable_level matches picked node's level
    const currentAction = grantableActions.find((a) => a.id === it.action_id)
    if (currentAction?.securable_level === pickedLevel) {
      fillIdx = i
      break // Prefer this row
    }
  }

  // Use the preferred or first fillable row
  if (fillIdx === -1 && fillIdxGeneral !== -1) {
    fillIdx = fillIdxGeneral
  }

  if (fillIdx >= 0) {
    // Fill the chosen row
    if (!bestAction) {
      // No best-fit action for this node type; just fill securable, keep action
      const newItems = currentItems.map((it, i) =>
        i === fillIdx ? { ...it, securable: pickedPath } : it,
      )
      return { newItems, hint: null }
    }

    const newItems = currentItems.map((it, i) =>
      i === fillIdx ? { action_id: bestAction.id, securable: pickedPath } : it,
    )
    return { newItems, hint: null }
  }

  // No fillable row; consider appending
  if (!bestAction) {
    // No best-fit action; show hint instead of appending
    return {
      newItems: currentItems,
      hint: 'No compatible action for this node type.',
    }
  }

  // Append a new row with best-fit action
  const newRow: ScenarioItem = { action_id: bestAction.id, securable: pickedPath }
  return { newItems: [...currentItems, newRow], hint: null }
}
