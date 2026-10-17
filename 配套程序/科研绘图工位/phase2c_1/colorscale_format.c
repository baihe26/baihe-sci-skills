#include <Origin.h>
// Thin native format access; both Color Scale directions share title formatting.
int p2c1_colorscale_format(string evidence_path, int set_font, double font_pt)
{
 GraphLayer gl = Project.ActiveLayer();
 GraphObject go = gl.GraphObjects("SPECTRUM1");
 if (!go) return -1;
 Tree tr; tr = go.GetFormat(FPB_ALL, FOB_ALL, TRUE, TRUE);
 if (!tr.Root) return -2;
 if (set_font) {
  int face = tr.Root.DimAxes.DimAxis2.NewAxes.NewAxis1.Labels.MajorLabels.Font.Face.nVal;
  tr.Root.DimAxes.DimAxis2.NewAxes.NewAxis1.Title.Font.Face.nVal = face;
  tr.Root.DimAxes.DimAxis2.NewAxes.NewAxis1.Title.Font.Size.dVal = font_pt;
  tr.Root.DimAxes.DimAxis2.NewAxes.NewAxis2.Title.Font.Face.nVal = face;
  tr.Root.DimAxes.DimAxis2.NewAxes.NewAxis2.Title.Font.Size.dVal = font_pt;
  tr.Save(evidence_path+".before.xml",TRUE);
  if (!go.ApplyFormat(tr, TRUE, TRUE)) return -5;
  tr = go.GetFormat(FPB_ALL, FOB_ALL, TRUE, TRUE);
 }
 return tr.Save(evidence_path, TRUE) ? 1 : -6;
}
