import { CheckCircle2, CircleSlash2, Database } from 'lucide-react'
import { Vendor } from '../lib/api'

export function Vendors({ vendors }: { vendors: Vendor[] | null }) {
  return <div className="page vendors-page">
    <div className="page-title-row">
      <div><span className="section-kicker">OEM coverage</span><h1>Vendor Matrix</h1><p>Registered parser support across the DeepTrace recovery engine.</p></div>
      <span className="record-count">{vendors?.length ?? 0} registered</span>
    </div>
    {!vendors ? <div className="loading-state"><Database className="spin" size={25} /><p>Loading registered vendors…</p></div> : <section className="vendor-matrix">
      {vendors.map((vendor) => <article className="vendor-row" key={vendor.id}>
        <div className="vendor-identity"><span className={`vendor-mark ${vendor.id === 'hikvision' ? 'hik' : vendor.id === 'dahua' ? 'dah' : ''}`}>{vendor.vendor_name.slice(0, 1)}</span><div><strong>{vendor.vendor_name}</strong><small>{vendor.id}</small></div></div>
        <p>{vendor.vendor_description}</p>
        <span className={`support-badge ${vendor.is_fully_implemented ? 'supported' : 'detection-only'}`}>{vendor.is_fully_implemented ? <CheckCircle2 size={14} /> : <CircleSlash2 size={14} />}{vendor.is_fully_implemented ? 'Full parser' : 'Detection only'}</span>
      </article>)}
    </section>}
  </div>
}
