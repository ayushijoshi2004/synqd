import { createJiraTickets, updateActionItemStatus } from "./meetings"

// Local demo conversion only. Ticket metadata never changes task status.
export const createActionItemTickets = createJiraTickets
export { updateActionItemStatus }
