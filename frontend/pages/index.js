import { useEffect, useState } from 'react'

export default function Page(){
  const [data,setData] = useState([])
  const [sortKey,setSortKey] = useState(null)
  const [dir,setDir] = useState(1)
  const [filter,setFilter] = useState('')

  useEffect(()=>{ fetch('/brawlers.json').then(r=>r.json()).then(setData) },[])

  const sorted = [...data].filter(r=> JSON.stringify(r).toLowerCase().includes(filter.toLowerCase()))
  if(sortKey){
    sorted.sort((a,b)=>{
      const av = a[sortKey] || 0
      const bv = b[sortKey] || 0
      return (isNaN(av) || isNaN(bv)) ? String(av).localeCompare(String(bv)) * dir : (bv - av) * dir
    })
  }

  const toggleSort = (k)=>{
    if(k===sortKey) setDir(d=>-d)
    else{ setSortKey(k); setDir(-1) }
  }

  return (
    <div style={{padding:20,fontFamily:'Arial'}}>
      <h1>Brawlers</h1>
      <input placeholder="filter..." value={filter} onChange={e=>setFilter(e.target.value)} style={{marginBottom:10}} />
      <table border="1" cellPadding="6">
        <thead>
          <tr>
            <th onClick={()=>toggleSort('Brawler')}>Brawler</th>
            <th onClick={()=>toggleSort('Power')}>Power</th>
            <th onClick={()=>toggleSort('Trophies')}>Trophies</th>
            <th onClick={()=>toggleSort('Gadgets')}>Gadgets</th>
            <th onClick={()=>toggleSort('Star Powers')}>Star Powers</th>
            <th onClick={()=>toggleSort('Gears')}>Gears</th>
            <th onClick={()=>toggleSort('Points to MAX')}>Points to MAX</th>
            <th onClick={()=>toggleSort('Coins to MAX')}>Coins to MAX</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r,i)=>(
            <tr key={i}>
              <td>{r.Brawler}</td>
              <td>{r.Power}</td>
              <td>{r.Trophies}</td>
              <td>{r.Gadgets}</td>
              <td>{r['Star Powers']}</td>
              <td>{r.Gears}</td>
              <td>{r['Points to MAX']}</td>
              <td>{r['Coins to MAX']}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
