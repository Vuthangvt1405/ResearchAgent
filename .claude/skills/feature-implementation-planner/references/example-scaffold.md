# Example scaffold (Step 9)

This continues the "Apply Coupon to Order" plan in `example-output.md`, after the user approved it.

---

## Scaffold: Apply Coupon to Order

### 1. File tree
```
src/main/java/com/shop/
├── coupon/
│   ├── 🆕 CouponRepository.java
│   └── 🆕 CouponValidator.java
├── order/
│   ├── ✏️ Order.java                 (+ coupon, discountAmount)
│   ├── ✏️ OrderController.java       (+ 2 endpoints)
│   ├── ✏️ OrderService.java          (+ applyCoupon, removeCoupon)
│   ├── ✏️ OrderRepository.java       (+ findByPublicIdAndCustomerId)
│   └── dto/
│       ├── 🆕 ApplyCouponRequest.java
│       ├── 🆕 OrderPricingResponse.java
│       └── 🆕 AppliedCouponDto.java
└── common/
    └── ✏️ ErrorCode.java             (+ 6 codes)
src/main/resources/db/migration/
└── 🆕 V12__add_coupon_to_orders.sql  (NOT executed)
src/test/java/com/shop/order/
├── 🆕 ApplyCouponServiceTest.java    (Groups 1–5, S6)
├── 🆕 ApplyCouponIntegrationTest.java (Groups 6–7)
└── 🆕 ApplyCouponSecurityTest.java   (Groups S1–S5)
```

### Key snippets

**ApplyCouponRequest.java**: complete, because DTOs and declarative validation are structure, not logic.
```java
/** Request to apply a coupon to a pending order. */
public record ApplyCouponRequest(
    /** The code the customer typed; normalized (trim + uppercase) before lookup. */
    @NotBlank @Size(max = 32) @Pattern(regexp = "^\\s*[A-Za-z0-9_-]{1,32}\\s*$")
    String couponCode
) {}
```

**OrderController.java**: wiring only.
```java
@PutMapping("/{orderId}/coupon")
@RateLimited(permits = 10, per = "1m")                       // SEC6
public OrderPricingResponse applyCoupon(
        @AuthenticationPrincipal UserPrincipal user,         // SEC1
        @PathVariable String orderId,
        @Valid @RequestBody ApplyCouponRequest request) {
    return orderService.applyCoupon(user.id(), orderId, request.couponCode());
}

@DeleteMapping("/{orderId}/coupon")
public OrderPricingResponse removeCoupon(
        @AuthenticationPrincipal UserPrincipal user,
        @PathVariable String orderId) {
    return orderService.removeCoupon(user.id(), orderId);
}
```

**OrderService.java**: signatures and TODOs, no logic.
```java
@Transactional
public OrderPricingResponse applyCoupon(UUID customerId, String orderId, String rawCode) {
    // TODO(AC6, SEC2, S2): load order by publicId AND customerId; same 404 for missing and foreign
    // TODO(AC5, G3): reject non-PENDING orders — 409 ORDER_NOT_EDITABLE
    // TODO(AC1, G1): normalize code (trim + uppercase), look up coupon — 422 COUPON_NOT_FOUND
    // TODO(AC2, AC3, G1, G2): CouponValidator.validate(coupon, order)
    // TODO(AC7, G4): discount = min(calculated, subtotal), HALF_UP, scale 2
    // TODO(AC4, G5): replace any existing coupon
    // TODO(SEC7, G6): save with optimistic lock — 409 on stale version
    // TODO(SEC8, S6): audit log COUPON_APPLIED (never log the token)
    throw new UnsupportedOperationException("TODO: applyCoupon not implemented");
}

@Transactional
public OrderPricingResponse removeCoupon(UUID customerId, String orderId) {
    // TODO(US2, G5): ownership + PENDING check, clear coupon, discount = 0, audit log
    throw new UnsupportedOperationException("TODO: removeCoupon not implemented");
}
```

**ApplyCouponServiceTest.java**: every planned test, failing on purpose.
```java
@Nested
@DisplayName("Group 1 — Coupon must be valid (AC1, AC2)")
class CouponValidity {

    @BeforeEach
    void baseline() {
        // TODO baseline: PENDING order subtotal 120; coupon SUMMER10, 10%, active, expires tomorrow
    }

    @Test
    void should_apply_discount_when_coupon_is_valid() {
        // Given baseline · When apply "SUMMER10" · Then discount 12, total 108, coupon_id saved
        // Demonstrates: a valid coupon changes what the customer pays, by the right amount
        fail("TODO: not implemented");
    }

    @Test
    void should_reject_when_coupon_expired_one_second_ago() {
        // Changed: expiresAt = now − 1s · Expect: 422 COUPON_EXPIRED, total still 120, no save
        // Demonstrates: expiry is enforced at the exact boundary
        fail("TODO: not implemented");
    }
    // ... every other ✅ / ❌ from Group 1, then Groups 2–5, in plan order
}
```

### 2. Build & test result
- `mvn -q compile test-compile`: ✅ passes
- `mvn test`: 54 new tests ❌ failing (expected: Red), 212 existing tests ✅ still passing
- Migration `V12` created, **not executed**

### 3. TODO map
| TODO | Location | Plan reference |
|---|---|---|
| Ownership query + same 404 | `OrderService.java:48` | AC6, SEC2, S2 |
| PENDING check | `OrderService.java:49` | AC5, G3 |
| Normalize + lookup | `OrderService.java:50` | AC1, G1 |
| Expiry / active / minimum rules | `CouponValidator.java:15` | AC2, AC3, G1, G2 |
| Discount calc + cap | `OrderService.java:52` | AC7, G4 |
| Replace coupon | `OrderService.java:53` | AC4, G5 |
| Optimistic lock | `OrderService.java:54` | SEC7, G6 |
| Audit log | `OrderService.java:55` | SEC8, S6 |
| removeCoupon | `OrderService.java:61` | US2, G5 |

### 4. Suggested first test
`should_apply_discount_when_coupon_is_valid` (the Group 1 baseline ✅). It forces the core path to exist: load the order, find the coupon, calculate the discount, and save. Every other test builds on that.

---

## Verification checkpoint (Step 10): STOP

### Self-verification
| # | Check | Result |
|---|---|---|
| V1 | Files match "Files affected", with no extras | ✅ 7 new, 5 modified, 0 unexpected (`git status`) |
| V2 | Endpoints match the plan | ✅ `PUT` and `DELETE /api/v1/orders/{orderId}/coupon` |
| V3 | DTO fields match the plan | ✅ `ApplyCouponRequest` (1 field), `OrderPricingResponse` (6 fields), `AppliedCouponDto` (4 fields) |
| V4 | Migration matches 3.3 and was not executed | ✅ `V12` has `coupon_id` (FK RESTRICT), `discount_amount` (DEFAULT 0), index; Flyway not run |
| V5 | Security wiring present | ✅ JWT principal on both endpoints, `@RateLimited(10/1m)` on PUT |
| V6 | All planned tests exist | ✅ planned 54 / found 54, names identical |
| V7 | No logic leaked | ✅ all new method bodies contain only TODOs + `UnsupportedOperationException` |
| V8 | Build & tests | ✅ compile passes; 54 new tests failing; 212 existing tests passing |

### Please verify before I implement any logic
☐ File locations and class/method names look right for our codebase
☐ Endpoint URLs, HTTP methods, and status codes are what you want
☐ DTO fields (names, types, required) are final — the API contract is about to be locked in
☐ Migration DDL is correct (column types, nullability, FK rule, index)
☐ The test list is complete — any missing negative or security case?
☐ TODO map covers all the work

Reply **"verified"** to start implementing logic test-by-test (starting with `should_apply_discount_when_coupon_is_valid`), or tell me what to change in the scaffold.

_(The agent stops here. No logic is written until the user verifies.)_
