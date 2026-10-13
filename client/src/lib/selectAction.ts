import type { ActionDescriptor, NodeType } from '../types'

/** Maps a picked node type to the securable_level. */
export function nodeTypeToLevel(type: NodeType): string | null {
  switch (type) {
    case 'catalog':
      return 'catalog'
    case 'schema':
      return 'schema'
    case 'table':
    case 'view':
      return 'table'
    case 'volume':
      return 'volume'
    case 'function':
      return 'function'
    case 'model':
      return 'model'
    default:
      return null
  }
}

/**
 * Picks the first grantable action whose securable_level matches the given node type.
 * Falls back to the first grantable action if no match is found.
 */
export function selectActionForNode(
  type: NodeType,
  grantableActions: ActionDescriptor[],
): ActionDescriptor | null {
  const level = nodeTypeToLevel(type)
  if (!level) return null

  // Try to find an action with matching securable_level
  const matched = grantableActions.find((a) => a.securable_level === level)
  if (matched) return matched

  // Fall back to first grantable action
  return grantableActions.length > 0 ? grantableActions[0] : null
}

/**
 * Filter actions to get only those that are grantable (have grant_sql)
 * for the current tab.
 */
export function getGrantableActions(
  actions: ActionDescriptor[],
  tab: string,
): ActionDescriptor[] {
  return actions.filter((a) => a.tab === tab && a.grant_sql)
}
