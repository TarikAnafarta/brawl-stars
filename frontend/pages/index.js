import { useEffect, useState } from 'react'
import Head from 'next/head'

export default function Page(){
  // default sort: Trophies descending
  const [data,setData] = useState([])
  const [trophyDiffs,setTrophyDiffs] = useState([])
  const [historyCards, setHistoryCards] = useState([])
  const [historyError, setHistoryError] = useState(false)
  const [sortKey,setSortKey] = useState('Trophies')
  const [dir,setDir] = useState(1)
  const [filter,setFilter] = useState('')
  const [isMobile, setIsMobile] = useState(false)

  // Helper to capitalize first letter of each word and lowercase the rest; handles hyphenated names
  const capitalize = (s) => {
    if (s === null || s === undefined) return s
    const str = String(s).trim()
    if (str.length === 0) return str
    return str.split(/\s+/).map(word =>
      word.split('-').map(part => part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : part).join('-')
    ).join(' ')
  }

  // Parse timestamps like "2025-11-12 00:01 +03" into Date objects
  const parseTimestamp = (ts) => {
    if(!ts) return null
    try{
      const str = String(ts).trim()
      // match YYYY-MM-DD HH:MM [±HH[:MM]]
      const m = str.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?:\s*([+\-]\d{1,2})(?::?(\d{2}))?)?$/)
      if(!m) return new Date(str)
      const date = m[1], time = m[2], offHour = m[3], offMin = m[4] || '00'
      let offset = '+00'
      if(offHour){
        // normalize hour offset to two digits, e.g. +3 -> +03
        offset = offHour[0] + offHour.slice(1).padStart(2,'0')
      }
      const iso = `${date}T${time}:00${offset}:${offMin}`
      const d = new Date(iso)
      if(isNaN(d)) return new Date(str)
      return d
    }catch(e){
      return new Date(ts)
    }
  }

  // Keep only the 24 most-recent entries (by parsed timestamp), newest-first
  const getMostRecentEntries = (arr) => {
    if(!Array.isArray(arr)) return []
    const withDates = arr.map(item => ({...item, _tsDate: parseTimestamp(item?.timestamp)})).filter(x=>x && x._tsDate && !isNaN(x._tsDate))
    withDates.sort((a,b)=> b._tsDate - a._tsDate)
    return withDates.slice(0,24)
  }

  useEffect(()=>{ 
    Promise.all([
      fetch('/brawlers.json').then(r=>r.json()),
      fetch('/overrides.json').then(r=>r.json()).catch(()=>({})),
      fetch('/brawlers.prev.json').then(r=>r.json()).catch(()=>null),
      fetch('/hourly_changes.json').then(r=>r.json()).catch(()=>[])
    ]).then(([brows,ov,prev,history])=>{
      // history is expected to be an array of cards; store for rendering
      setHistoryCards(Array.isArray(history) ? getMostRecentEntries(history) : [])
      const merged = brows.map(b => ({...b, ...(ov[b.Brawler]||{})}))
      setData(merged)

      // compute trophy diffs between prev and current (by Brawler name)
      if(prev && Array.isArray(prev)){
        const prevMap = {}
        prev.forEach(p=>{ if(p && p.Brawler) prevMap[p.Brawler] = Number(p.Trophies) || 0 })
        const diffs = []
        merged.forEach(cur=>{
          const name = cur.Brawler
          // ignore any brawler rows that look like a pre-computed total
          if(!name || /total/i.test(String(name))) return
          const curT = Number(cur.Trophies) || 0
          if(prevMap.hasOwnProperty(name)){
            const delta = curT - (prevMap[name] || 0)
            if(delta !== 0){ diffs.push({Brawler: name, delta}) }
          }
        })
        setTrophyDiffs(diffs)
      } else {
        setTrophyDiffs([])
      }
    })
  },[])

  // Additional explicit fetch with logging to help debug visibility issues
  useEffect(()=>{
    fetch('/hourly_changes.json')
      .then(r => {
        if(!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(j => {
        if(!Array.isArray(j)){
          console.error('hourly_changes.json is not an array', j)
          setHistoryCards([])
          setHistoryError(true)
          return
        }
        // keep only the last 24 hours of hourly changes (newest first)
        setHistoryCards(getMostRecentEntries(j))
        setHistoryError(false)
      })
      .catch(err => {
        console.error('Failed to load /hourly_changes.json:', err)
        setHistoryCards([])
        setHistoryError(true)
      })
  },[])

  // Track viewport size for responsive layout tweaks
  useEffect(()=>{
    const update = ()=> setIsMobile(typeof window !== 'undefined' && window.innerWidth <= 720)
    update()
    window.addEventListener('resize', update)
    return ()=> window.removeEventListener('resize', update)
  },[])

  // exclude any rows that look like a total row (e.g. Brawler contains "total")
  const visible = data.filter(r=>{
    if(!r) return false
    const name = String(r.Brawler || '')
    if(/total/i.test(name)) return false
    return true
  })

  // improved filter: search only table content (values) and the Brawler name — do NOT search column names
  const query = (filter || '').trim().toLowerCase()
  const filtered = query ? visible.filter(r => {
    if(!r) return false
    const bname = String(r.Brawler || '').toLowerCase()
    if(bname.includes(query)) return true
    try{
      // Build search text from values only (exclude keys/column names)
      const valuesText = Object.values(r).map(v => String(v ?? '')).join(' ').toLowerCase()
      return valuesText.includes(query)
    }catch(_){
      return JSON.stringify(r).toLowerCase().includes(query)
    }
  }) : [...visible]

  const sorted = filtered
  if(sortKey){
    sorted.sort((a,b)=>{
      // if sorting by Trophies itself, use that as primary key respecting dir
      if(sortKey === 'Trophies'){
        const na = Number(a.Trophies) || 0
        const nb = Number(b.Trophies) || 0
        return (nb - na) * dir
      }

      // Primary: selected column
      const av = a[sortKey]
      const bv = b[sortKey]
      const na = Number(av)
      const nb = Number(bv)

      if(!isNaN(na) && !isNaN(nb)){
        if(nb !== na) return (nb - na) * dir
      } else {
        const cmp = String(bv).localeCompare(String(av))
        if(cmp !== 0) return cmp * dir
      }

      // Secondary: Trophies DESC (highest trophies first)
      const ta = Number(a.Trophies) || 0
      const tb = Number(b.Trophies) || 0
      return tb - ta
    })
  }

  const toggleSort = (k)=>{
    if(k===sortKey) setDir(d=>-d)
    else{ setSortKey(k); setDir(-1) }
  }

  const isSortable = (k)=>{
    // list of columns that should offer a sort button
    // Gadgets, Star Powers and Gears do not have sort controls; add Hypercharge as sortable
    const cols = ['Power','Trophies','Hypercharge','Points to MAX','Coins to MAX']
    return cols.includes(k)
  }

  // show a compact icon instead of the word 'Sort'
  const sortIcon = (k)=>{
    if(sortKey!==k) return '⇅'
    return dir===1 ? '↓' : '↑'
  }

  // totals should ignore the filter and always reflect all visible brawlers
  const totalTrophies = visible.reduce((s,r)=> s + (Number(r.Trophies) || 0), 0)
  const totalPointsToMax = visible.reduce((s,r)=> s + (Number(r['Points to MAX']) || 0), 0)
  const totalCoinsToMax = visible.reduce((s,r)=> s + (Number(r['Coins to MAX']) || 0), 0)

  // total delta for all trophy changes
  const totalDelta = trophyDiffs.reduce((s,d)=> s + (Number(d.delta) || 0), 0)

  // Helper: background color for Power cell
  const getPowerBg = (r)=>{
    const p11 = Number(r?.Power) === 11
    const hv = String(r?.Hypercharge ?? '').toLowerCase()
    const hasHyper = hv === 'yes' || hv === 'y' || hv === 'true' || hv === '1' || hv === '✓'
    if(p11 && hasHyper) return '#fa00fd'
    if(p11 && !hasHyper) return '#f8a123'
    return 'transparent'
  }

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <div className="page" style={{padding:16,fontFamily:'Arial'}}>
        <div style={{marginBottom:10, display:'flex',gap:8,alignItems:'center'}}>
          <input placeholder="filter..." value={filter} onChange={e=>setFilter(e.target.value)} style={{width:160,padding:6}} aria-label="filter" />
          <button onClick={()=>{ setFilter(''); setSortKey('Trophies'); setDir(1); }} aria-label="Reset filter and sort" style={{padding:'6px 10px'}}>Reset</button>
        </div>

        <div style={{display:'flex',flexDirection: isMobile ? 'column' : 'row',alignItems:'flex-start',gap:20}}>
          <div style={{flex:1}}>
            <div style={{overflowX: 'auto'}}>
              <table border="1" cellPadding="6" style={{width:'100%',borderCollapse:'collapse', minWidth: isMobile ? 460 : 720}}>
              {/* minWidth keeps table readable on desktop but allows horizontal scroll on small screens */}
               <thead>
                <tr>
                  <th>Brawler</th>
                  <th style={{whiteSpace:'nowrap'}}>
                    Power {isSortable('Power') && (
                      <button onClick={()=>toggleSort('Power')} aria-label="Sort by Power" style={{marginLeft:6,padding:'2px 6px',fontSize:12}}>{sortIcon('Power')}</button>
                    )}
                  </th>
                  <th style={{whiteSpace:'nowrap'}}>
                    Trophies {isSortable('Trophies') && (
                      <button onClick={()=>toggleSort('Trophies')} aria-label="Sort by Trophies" style={{marginLeft:6,padding:'2px 6px',fontSize:12}}>{sortIcon('Trophies')}</button>
                    )}
                  </th>
                  <th style={{whiteSpace:'nowrap'}}>
                    Hypercharge {isSortable('Hypercharge') && (
                      <button onClick={()=>toggleSort('Hypercharge')} aria-label="Sort by Hypercharge" style={{marginLeft:6,padding:'2px 6px',fontSize:12}}>{sortIcon('Hypercharge')}</button>
                    )}
                  </th>
                  <th>
                    <span className="stacked"><span>Star</span><span>Powers</span></span>
                  </th>
                  <th>Gadgets</th>
                  <th>Gears</th>
                  <th>
                    <span className="stacked"><span>Points</span><span>to</span><span>MAX</span></span>
                    {isSortable('Points to MAX') && (
                      <button onClick={()=>toggleSort('Points to MAX')} aria-label="Sort by Points to MAX" style={{marginLeft:6,padding:'2px 6px',fontSize:12}}>{sortIcon('Points to MAX')}</button>
                    )}
                  </th>
                  <th>
                    <span className="stacked"><span>Coins</span><span>to</span><span>MAX</span></span>
                    {isSortable('Coins to MAX') && (
                      <button onClick={()=>toggleSort('Coins to MAX')} aria-label="Sort by Coins to MAX" style={{marginLeft:6,padding:'2px 6px',fontSize:12}}>{sortIcon('Coins to MAX')}</button>
                    )}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r,i)=>(
                  <tr key={i}>
                    <td>{capitalize(r.Brawler)}</td>
                    <td style={{backgroundColor: getPowerBg(r), color: '#000'}}>{r.Power}</td>
                    <td>{r.Trophies}</td>
                    <td>{r.Hypercharge}</td>
                    <td>{r['Star Powers']}</td>
                    <td>{r.Gadgets}</td>
                    <td>{r.Gears}</td>
                    <td>{r['Points to MAX']}</td>
                    <td>{r['Coins to MAX']}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>

          <div style={{width: isMobile ? '100%' : 380, display:'flex', flexDirection:'column', gap:12, alignSelf:'flex-start', marginTop: isMobile ? 12 : 0}}>
            <div style={{height: isMobile ? 120 : 150, position:'relative', boxShadow:isMobile ? '0 6px 14px rgba(16,24,40,0.12)' : '0 8px 24px rgba(16,24,40,0.12)', border:isMobile ? '1px solid rgba(0,0,0,0.06)' : '1px solid rgba(0,0,0,0.08)', borderRadius:8, overflow:'hidden'}}>
              {/* Photo placed inside the card (semi-transparent) so it is the card background and cannot overflow */}
              <img src="/IMG_20250815_225636.jpg" alt="" style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',opacity:isMobile?0.45:0.55,pointerEvents:'none'}} />

              {/* Text content sits above the photo; no full white box so photo is visible through the card */}
              <div style={{position:'relative', padding:12, color:isMobile? '#000' : '#000', textShadow:isMobile? 'none' : '0 1px 0 rgba(255,255,255,0.6)'}}>
                <h3 style={{marginTop:0,fontSize: isMobile ? 15 : 18}}>Summary</h3>
                <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
                  <div>Total Trophies:</div>
                  <div style={{fontWeight:'bold'}}>{totalTrophies}</div>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
                  <div>Points to MAX:</div>
                  <div style={{fontWeight:'bold'}}>{totalPointsToMax}</div>
                </div>
                <div style={{display:'flex',justifyContent:'space-between'}}>
                  <div>Coins to MAX:</div>
                  <div style={{fontWeight:'bold'}}>{totalCoinsToMax}</div>
                </div>
              </div>
            </div>

            {/* Show latest hourly change card if available */}
            {historyCards && historyCards.length>0 ? (
              <div style={{boxShadow:isMobile ? '0 6px 18px rgba(16,24,40,0.06)' : '0 10px 28px rgba(16,24,40,0.12)', border:'1px solid rgba(0,0,0,0.08)', borderRadius:8, padding:12, backgroundColor:'#e8f3fb'}}>
                <h4 style={{marginTop:0}}>Recent trophy changes (most recent 24)</h4>
                <div style={{paddingRight:6, display:'flex', flexDirection:'column', gap:10}}>
                  {historyCards.map((card,ci)=>(
                    <div key={ci} style={{padding:10, borderRadius:8, backgroundColor:isMobile? '#dceffb' : '#cfeafc', boxShadow:'inset 0 0 0 1px rgba(0,0,0,0.03)'}}>
                      <div style={{fontSize:13, marginBottom:6, color:'#666'}}>{card.timestamp}</div>
                      <div>
                        {card.lines && card.lines.map((L,i)=> (
                          <div key={i} style={{display:'flex',justifyContent:'space-between'}}>
                            <div>{L.split(' ')[0]}</div>
                            <div style={{color: L.includes('+') ? 'green' : L.includes('-') ? 'red' : 'inherit'}}>{L.split(' ').slice(1).join(' ')}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{display:'flex', justifyContent:'space-between', fontWeight:'bold', marginTop:6}}>
                        <div>TOTAL</div>
                        <div style={{color: card.total>0 ? 'green' : card.total<0 ? 'red' : 'inherit'}}>{card.total>0?`+${card.total}`:card.total}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{boxShadow:'0 6px 18px rgba(16,24,40,0.04)', border:'1px dashed rgba(0,0,0,0.04)', borderRadius:8, padding:12, backgroundColor:'#fff'}}>
                <div style={{color: historyError ? 'red' : '#666'}}> {historyError ? 'Could not load hourly_changes.json — check console/network' : 'No hourly changes available'}</div>
              </div>
            )}

            {trophyDiffs && trophyDiffs.length>0 && (
              <div style={{boxShadow:'0 6px 18px rgba(16,24,40,0.08)', border:'1px solid rgba(0,0,0,0.06)', borderRadius:8, padding:12, backgroundColor:'#fff'}}>
                <h4 style={{marginTop:0}}>Trophy changes (since last fetch)</h4>
                <div>
                  {trophyDiffs.map((d,i)=>(
                     <div key={i} style={{display:'flex',justifyContent:'space-between',fontSize:13}}>
                      <div>{capitalize(d.Brawler)}</div>
                       <div style={{color: d.delta>0 ? 'green' : 'red'}}>{d.delta>0?`+${d.delta}`:d.delta}</div>
                     </div>
                   ))}
                </div>

                <div style={{borderTop:'1px solid rgba(0,0,0,0.06)', marginTop:8, paddingTop:8, display:'flex', justifyContent:'space-between', fontWeight:'bold'}}>
                  <div>TOTAL</div>
                  <div style={{color: totalDelta>0 ? 'green' : totalDelta<0 ? 'red' : 'inherit'}}>{totalDelta>0?`+${totalDelta}`:totalDelta}</div>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      <style jsx>{`
        .page{ background:#eef8fb; min-height:100vh; min-height:100dvh; }
        .stacked span{ display:inline; }
        @media (max-width: 720px){
          .page{ background:#ffffff; }
          th, td{ font-size:14px; }
          .stacked span{ display:block; line-height:1.05; }
        }
      `}</style>
    </>
  )
}
