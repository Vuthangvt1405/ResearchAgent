// Vendor copy of Chainlit 2.12's own shadcn/ui progress (from its frontend source map), so every
// Tailwind class here is one Chainlit's prebuilt CSS already contains (A2, AC9).
import { cn } from '@/lib/utils';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import * as React from 'react';

const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  // value is passed on (stock shadcn drops it), so screen readers get aria-valuenow
  <ProgressPrimitive.Root
    ref={ref}
    value={value}
    className={cn(
      'relative h-4 w-full overflow-hidden rounded-full bg-secondary',
      className
    )}
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="h-full w-full flex-1 bg-primary transition-all"
      style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
    />
  </ProgressPrimitive.Root>
));
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
