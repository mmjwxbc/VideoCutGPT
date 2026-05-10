import React from 'react';
import { Moon, SunMedium } from 'lucide-react';

import { cn } from '../lib/utils';
import { useTheme } from '../theme/ThemeProvider';

interface ThemeToggleProps {
  className?: string;
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ className }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={cn(
        'theme-transition inline-flex h-10 items-center gap-2 rounded-full border px-3 text-[12px] font-medium',
        'border-app bg-app-surface text-app-secondary hover:border-app-strong hover:text-app-primary',
        className,
      )}
      aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
    >
      {theme === 'dark' ? <SunMedium className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
    </button>
  );
};

export default ThemeToggle;

