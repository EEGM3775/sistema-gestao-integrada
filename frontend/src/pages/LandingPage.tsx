import React from 'react'
import LandingHeader from '@/components/layout/LandingHeader'
import LandingFooter from '@/components/layout/LandingFooter'
import HeroSection from '@/components/HomeSections/HeroSection'
import ModulesSection from '@/components/HomeSections/ModulesSection'
import SocialProofSection from '@/components/HomeSections/SocialProofSection'
import SecuritySection from '@/components/HomeSections/SecuritySection'
import FinalCTASection from '@/components/HomeSections/FinalCTASection'

const LandingPage: React.FC = () => {
  return (
    <>
      <LandingHeader />
      <main>
        <HeroSection />
        <ModulesSection />
        <SocialProofSection />
        <SecuritySection />
        <FinalCTASection />
      </main>
      <LandingFooter />
    </>
  )
}

export default LandingPage
