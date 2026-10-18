// Заголовок страницы с кнопками действий. Верхняя панель с меню находится в layout.tsx (AppBar).
export default function AppHeader({ title, actions }: { title: string; actions?: React.ReactNode }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
