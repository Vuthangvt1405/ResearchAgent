# Example output

**Raw requirement from the user (a pasted Slack message from the marketing lead):**
> "We want customers to be able to use discount codes when they buy. Marketing should be able to create codes, like 10% off or $20 off, with an end date, and some codes only work if the order is big enough. Also we don't want people abusing it. Need this before the Black Friday campaign."

---

# Discount Coupons

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | **Customer** (applies codes), **Marketing admin** (creates codes) |
| Goals | Customer: pay less using a code. Marketing: create and control campaign codes |
| Business value | Drive Black Friday sales via campaigns *(stated: deadline is Black Friday)* |
| Rules (stated) | Types: percentage or fixed amount · has an end date · optional minimum order amount |
| Rules (assumed) | One coupon per order *(assumption)* · only on unpaid orders *(assumption)* · discount can't exceed order total *(assumption)* |
| Data | Coupon (code, type, value, end date, min order), Order (subtotal, discount, total) |
| Ambiguities | "abusing it": rate limiting? usage limits per customer? total uses? · "end date": inclusive? which timezone? · can codes stack? · can admins edit or deactivate codes? |

## Estimation Log

First pass: the requirement naturally falls into two big candidate stories, both too large.

| Candidate story | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Marketing manages coupons (create, deactivate) | Medium | Medium | High | 13 | ✂️ Split by operation |
| ↳ Story 1: Create discount coupon | Medium | Low | Medium | 5 | ✅ Keep |
| ↳ Story 4: Deactivate coupon before expiry | Low | Medium (Q3) | Low | 2 | ✅ Keep, pending Q3 |
| Customer uses coupon at checkout (apply, replace, remove, abuse protection) | High | High (7 open questions) | High | 21 | ✂️ Split by operation |
| ↳ Story 2: Apply discount coupon (incl. replace + abuse protection) | High | Medium | Medium | 8 | ⚠️ At the limit, keep |
| ↳ Story 3: Remove applied coupon | Low | Low | Low | 2 | ✅ Keep |

Notes:
- Story 2 keeps the abuse protection (AC9, AC10) on purpose. Splitting it out would let an unprotected coupon feature ship on Black Friday.
- **Story 2 is at the limit (8).** If the team estimates it higher, or Q1 adds usage limits, split it by business rule: **2a** apply a basic coupon (valid / unknown / expired / paid order, plus security) and **2b** minimum order and the discount cap.
- The children add up to less than the parents (17 vs 34), because splitting removed most of the uncertainty.

## Ticket Structure
```
Epic: Discount Coupons for Black Friday   (total: 17 points)
├── Story 1: Create discount coupon (admin)            (5 pts, Highest, depends on: —)
├── Story 2: Apply discount coupon to pending order    (8 pts ⚠️ at limit, Highest, depends on: Story 1)
├── Story 3: Remove applied coupon from order          (2 pts, High, depends on: Story 2)
└── Story 4: Deactivate coupon before expiry (admin)   (2 pts, Medium, depends on: Story 1) — pending Q3
```
Story 1 comes first, because customers can't apply codes until codes exist.

---

## Story 2: Apply discount coupon to pending order

**Summary:** Apply discount coupon to pending order
**Type:** Story | **Epic:** Discount Coupons for Black Friday | **Priority:** Highest | **Labels:** `checkout`, `black-friday` | **Components:** Orders, Checkout
**Story points (suggested):** 8 ⚠️ at the limit. Complexity High (pricing, rounding, security), Uncertainty Medium, Effort Medium. If the team estimates it above 8, split it into 2a/2b as shown in the Estimation Log.

### User Story
As a **logged-in customer**, I want to **apply a discount code to my order before paying**, so that **I pay the discounted campaign price**.

### Background
Marketing is running Black Friday campaigns that rely on discount codes. Today there is no way to enter a code at checkout, so campaigns can only be run as manual price changes. This story lets customers enter a code that marketing created (Story 1) and see the discounted total before payment.

### Acceptance Criteria

**AC1 — Valid coupon reduces the total**
Given my unpaid order has a subtotal of $120.00
And the coupon "SUMMER10" is active, gives 10% off, and has not expired
When I apply "SUMMER10"
Then I see a discount of $12.00 and a new total of $108.00
And the coupon "SUMMER10" is shown as applied

**AC2 — Code is not case-sensitive and ignores spaces** *(assumption)*
Given the coupon "SUMMER10" exists
When I enter " summer10 "
Then it is applied the same as "SUMMER10"

**AC3 — Unknown code**
Given no coupon "NOPE10" exists
When I apply "NOPE10"
Then I see "This code is not valid"
And my total is unchanged

**AC4 — Expired coupon**
Given the coupon "SUMMER10" ended yesterday
When I apply it
Then I see "This code has expired"
And my total is unchanged

**AC5 — Minimum order not met**
Given the coupon "BIG20" requires a minimum order of $50.00
And my subtotal is $49.99
When I apply "BIG20"
Then I see "Add $0.01 more to use this code"
And my total is unchanged
*(At exactly $50.00 the coupon applies: the minimum is inclusive, see Q2.)*

**AC6 — Discount never exceeds the order total** *(assumption)*
Given my subtotal is $15.00
And the coupon "FLAT20" gives $20.00 off
When I apply it
Then the discount is $15.00 and the total is $0.00

**AC7 — One coupon per order** *(assumption)*
Given "SUMMER10" is already applied to my order
When I apply a different valid coupon "BIG20"
Then "BIG20" replaces "SUMMER10" and the total is recalculated
And if "BIG20" is invalid, "SUMMER10" stays applied

**AC8 — Paid orders can't be changed**
Given my order is already paid, cancelled, or shipped
When I try to apply any coupon
Then I see "This order can no longer be changed"
And the order is unchanged

**AC9 — Security: only my own orders**
Given an order belongs to another customer
When I try to apply a coupon to it
Then I get the same "Order not found" response as for an order that doesn't exist
And that order is unchanged

**AC10 — Security: brute-force protection**
Given I have tried 10 codes in the last minute
When I try an 11th code
Then I see "Too many attempts, please try again in a minute"
And the code is not checked

### Developer Notes
- **Context & intent:** the campaign launches on Black Friday, so correctness of the price matters more than flexibility. When the ticket doesn't cover a case, prefer rejecting the coupon over giving a wrong discount.
- **Affected areas (likely):** orders module, checkout page price summary, and the coupon data created in Story 1. *(assumption: verify against the codebase)*
- **Business rule details:**
  - Check order: ownership → order status → coupon exists → active → not expired → minimum met. This order of checks means users only see messages about orders they own.
  - Percentage discounts: round half-up to 2 decimals (15% of $33.33 = $5.00).
  - Store the discount amount on the order when it is applied, so editing the coupon later doesn't change existing orders' prices.
- **Edge cases to watch:** the coupon expiring between apply and payment (see Q4), double-clicking "Apply", and the cart changing after a coupon is applied (see Q5).
- **Security considerations:** never trust a price or discount sent by the client; always calculate it on the server. Don't expose coupon rules (e.g. the minimum amount) beyond the error message. Log coupon applications for audit, but never log auth tokens.
- **Testing hints:** QA needs coupons in each state (active, expired, inactive, with a minimum, fixed amount larger than the order) and orders in each status (pending, paid, cancelled, shipped), plus two customer accounts for AC9.
- **Related:** Story 1 (coupon creation) · `[link to checkout Figma]` · `[link to Black Friday campaign brief]`

### Out of Scope
- Using more than one coupon on the same order
- Coupon usage limits (per customer or in total). Pending Q1. If needed, this becomes its own story, because adding it here would push Story 2 above 8 points
- Free-shipping coupons or "buy X get Y" deals
- Showing available coupons to the customer
- Coupon reporting for marketing

### Dependencies
- Story 1 (Create discount coupon) must be done first
- Checkout page design for the coupon input and its error states (Design team)

### Open Questions
- [ ] Q1: Can a customer use the same code on multiple orders? Is there a total usage limit (e.g. first 500 uses)? (@Marketing lead)
- [ ] Q2: Is the minimum order amount inclusive ($50.00 qualifies for a $50 minimum)? (@Marketing lead)
- [ ] Q3: Should admins be able to deactivate a code early, e.g. if it leaks? (@Marketing lead)
- [ ] Q4: If a code expires after it's applied but before payment, should the discount still be honored? (@PO)
- [ ] Q5: If items are removed and the order drops below the minimum, should the coupon be removed automatically? (@PO)
- [ ] Q6: Which timezone defines the end date, the store's or UTC? (@PO)
- [ ] Q7: Are separate error messages ("expired" vs "not valid") acceptable, given they reveal that a code exists? (@Security / PO)

---

## Story 1: Create discount coupon (admin) *(summary form; it would get the full template above)*

**User Story:** As a **marketing admin**, I want to **create a discount code with a type, value, end date, and optional minimum order**, so that **I can launch campaigns without asking developers**.

**AC headlines:** AC1 create a percentage coupon · AC2 create a fixed-amount coupon · AC3 code must be unique (case-insensitive) · AC4 percentage must be 1–100 · AC5 fixed amount must be > 0 · AC6 end date must be in the future · AC7 code is 3–32 characters, letters/digits/`-`/`_` only · AC8 only users with the marketing-admin role can create codes · AC9 every creation is audit-logged with who and when.

---

## Open Questions (all stories)
Q1–Q7 above, plus:
- [ ] Q8: Who besides marketing admins may create coupons? (@PO)
- [ ] Q9: Should Jira tickets be written in English for the whole team? (@Team lead)
