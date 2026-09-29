import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { MissionControl } from './pages/MissionControl'
import { StudentOperations } from './pages/StudentOperations'
import { LearningAnalytics } from './pages/LearningAnalytics'
import { CallQuality } from './pages/CallQuality'
import { FinancialOperations } from './pages/FinancialOperations'
import { TeamManagement } from './pages/TeamManagement'
import { ResearchEvidence } from './pages/ResearchEvidence'
import { Infrastructure } from './pages/Infrastructure'
import { Communications } from './pages/Communications'
import { Settings } from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/mission-control" replace />} />
        <Route path="mission-control" element={<MissionControl />} />
        <Route path="students" element={<StudentOperations />} />
        <Route path="learning" element={<LearningAnalytics />} />
        <Route path="calls" element={<CallQuality />} />
        <Route path="finance" element={<FinancialOperations />} />
        <Route path="team" element={<TeamManagement />} />
        <Route path="research" element={<ResearchEvidence />} />
        <Route path="infrastructure" element={<Infrastructure />} />
        <Route path="communications" element={<Communications />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
