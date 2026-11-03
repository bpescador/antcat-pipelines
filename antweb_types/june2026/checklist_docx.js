// checklist_docx.js -- turns checklist.json into type_reconciliation_checklist.docx with live links (npm package docx).
// Recovered verbatim on 2026-11-03 from the chat "Automating type specimen linking between
// Antcat and Antweb" (claude.ai chat 7b114e80, 8 Jun 2026, turn 37), where it ran as an inline step.
// One-off: paths and file names are the June chat's (/tmp/work, /mnt/user-data/outputs, prot.jsonl).
// Kept for the record; not maintained. See antweb_types/README.md.

const fs=require('fs');
const {Document,Packer,Paragraph,TextRun,ExternalHyperlink,HeadingLevel,BorderStyle,AlignmentType}=require('docx');
const d=JSON.parse(fs.readFileSync('/tmp/work/checklist.json','utf8'));

const children=[];
children.push(new Paragraph({heading:HeadingLevel.HEADING_1,children:[new TextRun(d.title)]}));
children.push(new Paragraph({spacing:{after:200},children:[new TextRun({text:d.subtitle,italics:true,color:"555555"})]}));

for(const sec of d.sections){
  children.push(new Paragraph({heading:HeadingLevel.HEADING_2,
    border:{bottom:{style:BorderStyle.SINGLE,size:6,color:"2E75B6",space:1}},
    children:[new TextRun(sec.title)]}));
  children.push(new Paragraph({spacing:{after:120},children:[new TextRun({text:sec.intro,color:"555555"})]}));
  for(const e of sec.entries){
    children.push(new Paragraph({spacing:{before:160,after:40},children:[new TextRun({text:e.head,bold:true})]}));
    for(const ln of e.lines){
      const warn=ln.startsWith('\u26a0');
      children.push(new Paragraph({spacing:{after:20},children:[new TextRun({text:ln,color:warn?"B00000":"000000",bold:warn})]}));
    }
    // links line
    const runs=[];
    e.links.forEach((lk,idx)=>{
      if(idx>0) runs.push(new TextRun({text:"     "}));
      if(lk.url){
        runs.push(new ExternalHyperlink({link:lk.url,children:[new TextRun({text:lk.label,style:"Hyperlink",color:"0563C1",underline:{}})]}));
      } else {
        runs.push(new TextRun({text:lk.label+" (no link)",color:"999999"}));
      }
    });
    children.push(new Paragraph({spacing:{after:40},children:runs}));
    children.push(new Paragraph({spacing:{after:120},children:[new TextRun({text:e.verdict,color:"333333"})]}));
  }
}

const doc=new Document({
  styles:{default:{document:{run:{font:"Arial",size:21}}},
    paragraphStyles:[
      {id:"Heading1",name:"Heading 1",basedOn:"Normal",next:"Normal",quickFormat:true,
        run:{size:30,bold:true,font:"Arial"},paragraph:{spacing:{before:120,after:160},outlineLevel:0}},
      {id:"Heading2",name:"Heading 2",basedOn:"Normal",next:"Normal",quickFormat:true,
        run:{size:25,bold:true,font:"Arial",color:"1F4E79"},paragraph:{spacing:{before:240,after:80},outlineLevel:1}},
    ]},
  sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}]
});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync('/mnt/user-data/outputs/type_reconciliation_checklist.docx',b);console.log('written');});
