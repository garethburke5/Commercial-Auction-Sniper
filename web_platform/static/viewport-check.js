document.querySelector('#phone').onclick=()=>document.body.classList.remove('desktop');
document.querySelector('#desktop').onclick=()=>document.body.classList.add('desktop');
document.querySelector('#platform').onclick=()=>document.querySelector('iframe').src='../?viewport-check='+Date.now();
document.querySelector('#scanner').onclick=()=>document.querySelector('iframe').src='https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/?embed=true';
document.querySelector('#fees').onclick=()=>document.querySelector('iframe').src='../auctioneers/?viewport-check='+Date.now();

document.querySelector('#property').onclick=()=>document.querySelector('iframe').src='../property/557473a470eb669ba8b9/unit-10-south-street-ilkeston-derbyshire-de75-5qe/?viewport-check='+Date.now();
document.querySelector('#calendar').onclick=()=>document.querySelector('iframe').src='../auctions/?viewport-check='+Date.now();
document.querySelector('#plans').onclick=()=>document.querySelector('iframe').src='../plans/?viewport-check='+Date.now();

document.querySelector('#research').onclick=()=>document.querySelector('iframe').src='https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/~/+/?embed=true&view=due-diligence';
document.querySelector('#glossary').onclick=()=>document.querySelector('iframe').src='../glossary/?viewport-check='+Date.now();

for(const [id,path] of [['account','account'],['deals','deals'],['owner','admin/deals']])document.getElementById(id).onclick=()=>document.querySelector('iframe').src='../'+path+'/?viewport-check='+Date.now();
