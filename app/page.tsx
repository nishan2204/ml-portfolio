import Hero from '@/components/Hero'
import About from '@/components/About'
import SkillsBar from '@/components/SkillsBar'
import Footer from '@/components/Footer'
import ProjectSection from '@/components/ProjectSection'
import SchedulingDemo from '@/components/demos/SchedulingDemo'
import RevenueForecastDemo from '@/components/demos/RevenueForecastDemo'
import FindingsAgentDemo from '@/components/demos/FindingsAgentDemo'
import SegmentationDemo from '@/components/demos/SegmentationDemo'
import InsightNarrativeDemo from '@/components/demos/InsightNarrativeDemo'
import IoTMaintenanceDemo from '@/components/demos/IoTMaintenanceDemo'
import ABTestDemo from '@/components/demos/ABTestDemo'
import SelfHealingPipelineDemo from '@/components/demos/SelfHealingPipelineDemo'
import LTVChurnDemo from '@/components/demos/LTVChurnDemo'
import CapacityPlanningDemo from '@/components/demos/CapacityPlanningDemo'
import EDAQualityDemo from '@/components/demos/EDAQualityDemo'
import FinancialScenarioDemo from '@/components/demos/FinancialScenarioDemo'
import EHRAccessDemo from '@/components/demos/EHRAccessDemo'
import { projects } from '@/lib/projects'

function getDemo(id: number) {
  switch (id) {
    case 1:  return <SchedulingDemo />
    case 2:  return <RevenueForecastDemo />
    case 3:  return <FindingsAgentDemo />
    case 4:  return <SegmentationDemo />
    case 5:  return <InsightNarrativeDemo />
    case 6:  return <IoTMaintenanceDemo />
    case 7:  return <ABTestDemo />
    case 8:  return <SelfHealingPipelineDemo />
    case 9:  return <LTVChurnDemo />
    case 10: return <CapacityPlanningDemo />
    case 11: return <EDAQualityDemo />
    case 12: return <FinancialScenarioDemo />
    case 13: return <EHRAccessDemo />
    default: return null
  }
}

export default function Home() {
  return (
    <main>
      <Hero />
      <About />
      <SkillsBar />
      <section id="projects">
        {projects.map((project) => (
          <ProjectSection key={project.id} project={project}>
            {getDemo(project.id)}
          </ProjectSection>
        ))}
      </section>
      <Footer />
    </main>
  )
}
