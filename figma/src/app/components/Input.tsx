import { InputHTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={clsx(
          'w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder:text-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all',
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';
