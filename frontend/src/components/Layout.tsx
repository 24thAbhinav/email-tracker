import { NavLink, Outlet } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'nav-link active' : 'nav-link'

export default function Layout() {
  return (
    <div className="layout">
      <nav className="nav">
        <span className="brand">Job Tracker</span>
        <div className="nav-links">
          <NavLink to="/" end className={navClass}>
            Dashboard
          </NavLink>
          <NavLink to="/settings" className={navClass}>
            Settings
          </NavLink>
        </div>
      </nav>
      <main>
        <Outlet />
      </main>
    </div>
  )
}
