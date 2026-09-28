document.querySelector('#phone').onclick=()=>document.body.classList.remove('desktop');
document.querySelector('#desktop').onclick=()=>document.body.classList.add('desktop');
document.querySelector('#platform').onclick=()=>document.querySelector('iframe').src='../?viewport-check='+Date.now();
document.querySelector('#scanner').onclick=()=>document.querySelector('iframe').src='https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/?embed=true';
document.querySelector('#fees').onclick=()=>document.querySelector('iframe').src='../auctioneers/?viewport-check='+Date.now();
