import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import prettierConfig from 'eslint-config-prettier'

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**', 'coverage/**']
  },

  // TS rules everywhere we have TS: .ts files plus the <script> blocks of SFCs.
  ...tseslint.configs.recommended,
  ...tseslint.config({
    files: ['**/*.vue'],
    extends: [...tseslint.configs.recommended]
  }),

  // Correctness-focused Vue rules (not the stylistic presets — Prettier owns layout).
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.vue']
      }
    }
  },

  {
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }
      ],
      // Prefer `import type { X }` for type-only imports (tree-shaking friendly).
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' }
      ],
      '@typescript-eslint/no-explicit-any': 'error'
    }
  },

  // Keep Prettier from fighting formatting rules — must stay last.
  prettierConfig
)
