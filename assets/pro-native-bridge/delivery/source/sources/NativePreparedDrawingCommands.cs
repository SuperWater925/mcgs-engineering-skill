// Native drawing command candidates. Prepare is read-only; native calls require the action Lease.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;
using System.IO;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal const string DrawingCommandProfileSha="bf27146170e0597942064eec574ffcec0d9ca5e95789ca8ea79d083fd4880a0f";
  const string DrawingRelative="coverage-20261101/usable-edit-0001/page-control-prep/drawing-command-abi-profile.v2.json";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void SelectControl(IntPtr self,IntPtr control,int append);
  static Dictionary<string,object> DrawingContract(Api api,Dictionary<string,object> action){
   string path=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"page-control-prep","drawing-command-abi-profile.v2.json");
   NativeMemory.Require(NativeMemory.Hash(path)==DrawingCommandProfileSha,"Native drawing command ABI contract changed.");
   var profile=Load(path);
   NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),api.Engine.ImageSha256,"NativePreparedDrawingCommands:8:editor")&&Convert.ToString(profile["template_profile_sha256"])==ProfileSha,"Native command and installed class ABI differ.");
   string direction=null;object after,directionValue;
   if(NativePageControlPreparation.Kind(action)=="control-layer"&&action.TryGetValue("after",out after)&&Map(after).TryGetValue("direction",out directionValue)){
    direction=Convert.ToString(directionValue);
    NativeMemory.Require(direction=="front"||direction=="back"||direction=="forward"||direction=="backward","Unknown native layer direction.");
   }
   var methods=Map(profile["methods"]);
   var routeOnlyFunctions=new HashSet<int>();
   var requiredFunctions=new HashSet<int>();
   int routed=0;
   foreach(object value in (IEnumerable)profile["commands"]){
    var row=Map(value);string role=Convert.ToString(row["name"]);
    if(direction!=null){
     var method=Map(methods[role]);int entry=Num(method["entry_rva"]),body=Num(method["body_rva"]);
     if(role!=direction){routeOnlyFunctions.Add(entry);routeOnlyFunctions.Add(body);continue;}
     requiredFunctions.Add(entry);requiredFunctions.Add(body);routed++;
    }
    IntPtr address=api.Engine.Address(Num(row["message_map_rva"]));
    NativeMemory.Require(NativeMemory.I32(address,0)==0x111&&NativeMemory.I32(address,4)==0&&NativeMemory.I32(address,8)==Num(row["command_id"])&&NativeMemory.I32(address,12)==Num(row["command_id"])&&NativeMemory.I32(address,16)==58&&NativeMemory.Ptr(address,20)==api.Engine.Address(Num(row["handler_entry_rva"])),"Original command routing/handler identity changed.");
   }
   if(direction!=null)NativeMemory.Require(routed==1,"Selected layer route is missing or ambiguous.");
   // Only disjoint command entry/body pairs are excluded. All shared,
   // class-specific and unclassified guards are still checked.
   routeOnlyFunctions.ExceptWith(requiredFunctions);
   foreach(object value in (IEnumerable)profile["code_guards"]){
    var row=Map(value);int entry=Num(row["rva"]);
    if(routeOnlyFunctions.Contains(entry))continue;
    RequireProfileCodeBytes(api.Engine,row,"drawing command code guard",DrawingRelative);requiredFunctions.Remove(entry);
   }
   NativeMemory.Require(requiredFunctions.Count==0,"Selected layer command is missing a code guard.");
   return profile;
  }
  static T DrawingBind<T>(Api api,Dictionary<string,object> profile,string method)where T:class{return api.Engine.Bind<T>(api.Engine.Address(Num(Map(Map(profile["methods"])[method])["entry_rva"])));}
  static void DrawingClass(Api api,Dictionary<string,object> profile,Node node){api.Type(node.Full);Dictionary<string,object> selected=null;foreach(object value in (IEnumerable)profile["classes"]){var row=Map(value);if(Convert.ToString(row["class_name"])==node.Class.Name)selected=row;}NativeMemory.Require(selected!=null,"Drawing command class contract is absent.");IntPtr vt=api.Engine.Address(Num(selected["primary_vtable_rva"]));foreach(var slot in Map(selected["slots"]))NativeMemory.Require(NativeMemory.Ptr(vt,4*Int32.Parse(slot.Key,CultureInfo.InvariantCulture))==api.Engine.Address(Num(slot.Value)),"A class-specific native group/layer virtual entry changed.");}
  static List<IntPtr> DrawingSelection(Api api,IntPtr view,IntPtr doc){var top=api.Shared.TopControls(doc);IntPtr list=NativeMemory.Add(view,0x164);NativeMemory.Require(NativeMemory.Ptr(list,0)==api.Engine.Address(0xD3FD70),"Drawing selected-list native class differs.");int count=NativeMemory.I32(list,12);NativeMemory.Require(count>=0&&count<=top.Count,"Drawing selected-list count differs.");var rows=new List<IntPtr>();IntPtr node=NativeMemory.Ptr(list,4),previous=IntPtr.Zero;for(int i=0;i<count;i++){NativeMemory.Require(node!=IntPtr.Zero&&NativeMemory.Ptr(node,4)==previous,"Drawing selected-list links differ.");IntPtr full=NativeMemory.Ptr(node,8);NativeMemory.Require(top.Contains(full)&&!rows.Contains(full),"Drawing selection contains another owner, nested object or duplicate.");rows.Add(full);previous=node;node=NativeMemory.Ptr(node,0);}NativeMemory.Require(node==IntPtr.Zero&&previous==NativeMemory.Ptr(list,8),"Drawing selection tail/count differ.");return rows;}
  static List<Node> DrawingTargets(Api api,Dictionary<string,object> action,IntPtr page,IntPtr doc){var rows=new List<Node>();var t=Map(action["target"]);foreach(object value in (IEnumerable)t["controls"]){var selector=new Dictionary<string,object>(Map(value));selector["page_id"]=t["page_id"];selector["page_name"]=t["page_name"];IntPtr actualPage,actualDoc;Node node=api.Locate(selector,out actualPage,out actualDoc);NativeMemory.Require(node.Path.Length==1&&actualPage==page&&actualDoc==doc&&!rows.Exists(delegate(Node old){return old.Full==node.Full;}),"Drawing command needs distinct exact top-level controls in its target page.");rows.Add(node);}return rows;}
  static List<object> DrawingPayload(Api api,List<Node> flat){var rows=new List<object>();foreach(Node node in flat)using(var collector=new NativeTypedPropertyCollector(api.Engine))rows.Add(new Dictionary<string,object>{{"complete",NativeMemory.Hex(node.Full)},{"properties",collector.Read(NativeMemory.Add(node.Full,4))}});return rows;}
  internal const string GroupCoordinateContract = "original-cell-coordinate-roles/v1";
  internal const string GroupFlattenContract = "original-cell-flatten/v1";
  static bool RequestsGroupCoordinateRoles(Dictionary<string,object> action) {
   string kind=NativePageControlPreparation.Kind(action);object after, marker;
   return (kind=="control-group"||kind=="control-ungroup")&&action.TryGetValue("after",out after)&&
          Map(after).TryGetValue("coordinate_contract",out marker)&&Object.Equals(marker,GroupCoordinateContract);
  }
  static List<object> GroupCoordinateRoles(Api api,Dictionary<string,object> profile,List<Node> nodes) {
   Dictionary<string,object> drawingBase=null;
   foreach(object entry in (IEnumerable)profile["classes"]) {
    var candidate=Map(entry);
    if(Object.Equals(candidate["class_name"],"CDrawObj")) {
     NativeMemory.Require(drawingBase==null,"The original drawing base coordinate role is ambiguous.");
     drawingBase=candidate;
    }
   }
   NativeMemory.Require(drawingBase!=null,"The original drawing base coordinate role is absent.");
   var slots=Map(drawingBase["slots"]);
   IntPtr baseTable=api.Engine.Address(Num(drawingBase["primary_vtable_rva"]));
   IntPtr toCell=api.Engine.Address(Num(slots["5"])),fromCell=api.Engine.Address(Num(slots["6"]));
   NativeMemory.Require(NativeMemory.Ptr(baseTable,20)==toCell&&NativeMemory.Ptr(baseTable,24)==fromCell,
      "The original drawing base coordinate slots changed.");
   var events=new NativePageDocumentProperties.Api(api.Engine,api.Context,api.Shared.Project);
   var animations=new NativeAnimationListEditing.Api(api.Engine);
   var roles=new List<object>();
   foreach(Node node in nodes) {
    DrawingClass(api,profile,node);
    bool drawControl=false;
    foreach(object baseRole in (IEnumerable)node.Class.Primary["bases"])
     drawControl|=Object.Equals(Map(baseRole)["rtti"],".?AVCDrawCtrl@@");
    IntPtr table=NativeMemory.Ptr(node.Full,0);
    string model="unverified";
    string kind=node.Class.Name;
    bool leaf=kind=="CDrawLine"||kind=="CDrawRect"||kind=="CDrawEllipse"||kind=="CDrawLabel";
    bool cell=kind=="CDrawCell"&&node.Class.TypeId==0x5039;
    if(!node.Class.External&&!drawControl&&(leaf||cell)&&
       !NativeControlEventEditing.HasStoredControlEvents(events,node.Full)&&!animations.HasItems(node.Full)) {
     if(cell)model="native-cell-container";
     else if(node.Children.Count==0&&NativeMemory.Ptr(table,20)==toCell&&NativeMemory.Ptr(table,24)==fromCell)
      model=kind=="CDrawLine"?"directed-line":"bounding-rectangle";
    }
    roles.Add(new Dictionary<string,object>{{"complete",NativeMemory.Hex(node.Full)},{"model",model}});
   }
   return roles;
  }
  static Dictionary<string,object> DrawingCapture(Api api,NativeReferencedPageEditing.Api references,
    Dictionary<string,object> action,Dictionary<string,object> profile) {
   IntPtr page=api.Shared.Page(Map(action["target"])),doc=NativeMemory.Ptr(page,NativeLayout.Offset("page.document")),view=api.View(doc);
   NativeMemory.Require(view!=IntPtr.Zero,"Original drawing commands require an already open drawing view; no project reopen is performed.");
   var selection=new List<string>();
   foreach(IntPtr pointer in DrawingSelection(api,view,doc))selection.Add(NativeMemory.Hex(pointer));
   var roots=api.Forest(doc);
   RequireKnownForest(roots,"whole-page drawing payload/reference command");
   var flat=new List<Node>(Flatten(roots));
   var forest=new List<object>();
   foreach(Node node in roots)forest.Add(Snapshot(api,node));
   var paths=new List<object>();
   foreach(Node node in flat)paths.Add(new Dictionary<string,object>{
    {"complete",NativeMemory.Hex(node.Full)},{"linker",references.Path(NativeMemory.Add(node.Full,4))}});
   var result=new Dictionary<string,object>{
    {"abi_profile_sha256",DrawingCommandProfileSha},{"page",api.Shared.PageSnapshot(page)},
    {"forest",forest},{"view_state",api.ViewState(doc)},
    {"history_store_projection",NativeHistoryStoreProjection.Prepare(api.Engine,doc).Before},
    {"selection",selection},{"control_properties",DrawingPayload(api,flat)},
    {"control_linkers",paths},{"reference_graph",NativeReferencedPageEditing.Graph(references)}};
   if(RequestsGroupCoordinateRoles(action)) {
    result["page_linker"]=references.Path(page);
    result["coordinate_roles"]=GroupCoordinateRoles(api,profile,flat);
    result["group_preimage_sha256"]=NativeUsableEditPermit.Digest(NativePageControlPreparation.Json(result));
   }
   return result;
  }
  internal static Dictionary<string,object> ReadDrawingCommand(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action) {
   var api=new Api(e,c,p);
   if(RequestsGroupCoordinateRoles(action)) {
    IntPtr page=api.Shared.Page(Map(action["target"]));
    DrawingTargets(api,action,page,NativeMemory.Ptr(page,NativeLayout.Offset("page.document")));
   }
   return DrawingCapture(api,new NativeReferencedPageEditing.Api(e,c,p),action,DrawingContract(api,action));
  }
  internal static INativePreparedPageControlEdit PrepareDrawingCommand(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new PreparedDrawingCommand(new Api(e,c,p),new NativeReferencedPageEditing.Api(e,c,p),action);}
  sealed class PreparedDrawingCommand:INativePreparedPageControlEdit {
   readonly NativeHistoryStoreProjection historyState;readonly Api api;readonly NativeReferencedPageEditing.Api references;readonly Dictionary<string,object> action,before,profile;readonly IntPtr page,doc,view,root;readonly List<Node> targets;readonly List<string> expectedTop=new List<string>();readonly Dictionary<string,string> oldPaths=new Dictionary<string,string>();readonly HashSet<string> removed=new HashSet<string>();readonly List<string> moved=new List<string>();readonly string kind,direction;readonly V0 command,update;readonly SelectControl select;readonly VI rootDirty,invalidate;readonly SaveData save;readonly NativeEngine.ThisInt modified;bool applied,disposed;Dictionary<string,object> after;
   internal PreparedDrawingCommand(Api value,NativeReferencedPageEditing.Api refs,Dictionary<string,object> a){api=value;references=refs;action=a;kind=NativePageControlPreparation.Kind(a);NativeMemory.Require(Convert.ToString(a["abi_profile_sha256"])==DrawingCommandProfileSha,"Drawing command action/profile differs.");profile=DrawingContract(api,a);page=api.Shared.Page(Map(a["target"]));doc=NativeMemory.Ptr(page,NativeLayout.Offset("page.document"));root=api.Shared.Shared.RootDoc();view=api.View(doc);NativeMemory.Require(view!=IntPtr.Zero,"Native drawing command needs its existing open view.");targets=DrawingTargets(api,a,page,doc);historyState=NativeHistoryStoreProjection.Prepare(api.Engine,doc);NativeMemory.Require(targets.Count>0,"Native command target set is empty.");string method;if(kind=="control-layer"){NativeMemory.Require(targets.Count==1,"Native layer command handles one explicit target per action.");direction=NativePageControlPreparation.Text(Map(a["after"]),"direction");NativeMemory.Require(direction=="front"||direction=="back"||direction=="forward"||direction=="backward","Unknown native layer direction.");method=direction;}else{NativeMemory.Require(kind=="control-group"||kind=="control-ungroup","Unknown original drawing command kind.");method=kind=="control-group"?"group":targets[0].Class.Name=="CDrawUnit"?"ungroup_unit":"ungroup";NativeMemory.Require(kind!="control-ungroup"||(targets.Count==1&&(targets[0].Class.Name=="CDrawUnit"||targets[0].Class.Name=="CDrawCell")),"Original ungroup requires one exact CDrawCell or CDrawUnit.");NativeMemory.Require(Map(a["after"]).ContainsKey("surviving_controls"),"Group/ungroup requires complete expected surviving_controls, including original native converted rectangles/properties/raw60.");}
    command=DrawingBind<V0>(api,profile,method);select=DrawingBind<SelectControl>(api,profile,"select");rootDirty=api.Shared.Shared.Bind<VI>("RootSetModified");invalidate=api.ViewBind<VI>("InvalidateView");update=api.ViewBind<V0>("UpdateView");save=api.Shared.Bind<SaveData>("standard","WindowSaveData");modified=api.Shared.Shared.Bind<NativeEngine.ThisInt>("RootIsModified");api.Shared.Slot(api.Context.WindowService,12,0x21733);before=DrawingCapture(api,references,a,profile);NativePageControlPreparation.Before(a,before);
    object planned;
    if(Map(a["after"]).TryGetValue("group_preimage_sha256",out planned)) {
     NativeMemory.Require(RequestsGroupCoordinateRoles(a),"A planned group edit needs a verified current coordinate contract.");
     NativeMemory.Require(Object.Equals(planned,before["group_preimage_sha256"]),
      "The drawing forest, properties, view or references changed after group planning.");
    } else NativeMemory.Require(!RequestsGroupCoordinateRoles(a),"A planned group edit lacks its original preimage.");
    if(kind=="control-group")foreach(Node selectedNode in targets)foreach(object valueRow in (IEnumerable)selectedNode.Class.Primary["bases"])NativeMemory.Require(Convert.ToString(Map(valueRow)["rtti"])!=".?AVCDrawCtrl@@","Original make-symbol handler rejects directly selected CDrawCtrl descendants; use an existing native Unit template or the appropriate compound-unit creation chain.");foreach(Node node in Flatten(api.Forest(doc))){DrawingClass(api,profile,node);oldPaths.Add(NativeMemory.Hex(node.Full),references.Path(NativeMemory.Add(node.Full,4)));}
    var top=api.Shared.TopControls(doc);foreach(IntPtr pointer in top)expectedTop.Add(NativeMemory.Hex(pointer));if(kind!="control-layer")foreach(Node target in targets)foreach(Node node in Flatten(new List<Node>{target}))NativeMemory.Require(!node.Class.External,"Original grouping external component context still needs a closed adapter.");if(kind=="control-layer"){string selected=NativeMemory.Hex(targets[0].Full);int index=expectedTop.IndexOf(selected),next=direction=="front"?top.Count-1:direction=="back"?0:direction=="forward"?Math.Min(index+1,top.Count-1):Math.Max(index-1,0);expectedTop.RemoveAt(index);expectedTop.Insert(next,selected);}else{foreach(Node node in api.Forest(doc))if(targets.Exists(delegate(Node chosen){return chosen.Full==node.Full;})){expectedTop.Remove(NativeMemory.Hex(node.Full));if(kind=="control-group"&&node.Class.Name!="CDrawCell")moved.Add(NativeMemory.Hex(node.Full));else{removed.Add(NativeMemory.Hex(node.Full));foreach(Node child in node.Children)moved.Add(NativeMemory.Hex(child.Full));}}if(kind=="control-group")expectedTop.Add("$created");else expectedTop.AddRange(moved);PreflightIncoming();ValidateExpectedSurvivors();}
    if(RequestsGroupCoordinateRoles(a))ValidateGroupPlan();
   }
   static List<int> ProjectMember(IList<int> source,IList<int> bounds,bool intoCell) {
    var projected=new List<int>();
    for(int edge=0;edge<4;edge++) {
     int axis=edge%2,width=checked(bounds[axis+2]-bounds[axis]);
     NativeMemory.Require(width>0,"Native group bounds have a degenerate axis.");
     int offset=intoCell?checked(source[edge]-bounds[axis]):source[edge];
     long numerator=(long)offset*(intoCell?10000:width),denominator=intoCell?width:10000;
     long absolute=(Math.Abs(numerator)+denominator/2)/denominator;
     long scaled=numerator<0?-absolute:absolute;
     projected.Add(intoCell?checked((int)scaled):checked((int)(bounds[axis]+scaled)));
    }
    return projected;
   }
   void ValidateGroupPlan() {
    bool grouping=kind=="control-group";
    string pagePath=Convert.ToString(before["page_linker"]);
    var coordinates=new Dictionary<string,string>();
    foreach(object value in (IEnumerable)before["coordinate_roles"]){var row=Map(value);coordinates.Add(Convert.ToString(row["complete"]),Convert.ToString(row["model"]));}
    if(grouping)NativeMemory.Require(targets.Count>=2,"Native group planning needs at least two members.");
    else NativeMemory.Require(coordinates[NativeMemory.Hex(targets[0].Full)]=="native-cell-container","Native ungroup planning needs a static original cell.");
    var after=Map(action["after"]);
    object flattenFlag;
    bool flatten=after.TryGetValue("flatten_selected_cells",out flattenFlag)&&Object.Equals(flattenFlag,true);
    NativeMemory.Require(flatten==(grouping&&removed.Count>0)&&(!after.ContainsKey("flatten_selected_cells")||flatten),
       "Grouping selected static cells requires explicit flatten_selected_cells.");
    var directOrder=new List<int>();
    var parentBounds=new Dictionary<string,int[]>();
    foreach(Node target in targets){
     directOrder.Add(target.Path[0]);
     if(!flatten||!removed.Contains(NativeMemory.Hex(target.Full)))continue;
     NativeMemory.Require(coordinates[NativeMemory.Hex(target.Full)]=="native-cell-container"&&target.Children.Count>0,
       "Selected cell has events, animations or no retained static members.");
     var bounds=NativePageControlAbi.Rectangle(target.Full);
     foreach(Node child in target.Children)parentBounds.Add(NativeMemory.Hex(child.Full),bounds);
    }
    var documentOrder=new List<int>(directOrder);documentOrder.Sort();
    NativePageControlPreparation.Same(documentOrder,directOrder,"Planned native selection must follow the original document order.");
    NativeMemory.Require(moved.Count>0,"Native group planning needs at least one retained member.");
    var properties=new Dictionary<string,object>();
    foreach(object value in (IEnumerable)before["control_properties"]){var row=Map(value);properties.Add(Convert.ToString(row["complete"]),row["properties"]);}
    var original=new Dictionary<string,Dictionary<string,object>>();
    foreach(var row in FlatSnapshot(before["forest"]))original.Add(Convert.ToString(row["complete"]),row);
    var outer=grouping?new[]{Int32.MaxValue,Int32.MaxValue,Int32.MinValue,Int32.MinValue}:NativePageControlAbi.Rectangle(targets[0].Full);
    var memberCoordinates=new Dictionary<string,List<int>>();
    foreach(string address in moved) {
     var row=original[address];
     NativeMemory.Require(coordinates[address]=="bounding-rectangle"||coordinates[address]=="directed-line", "The original member has an event, animation or unverified group transform.");
     NativeMemory.Require(oldPaths[address]==pagePath+"."+Convert.ToString(row["name"]),"The original member linker is not page-scoped.");
     var rect=Integers(row["rectangle"]);
     int[] parent;
     if(parentBounds.TryGetValue(address,out parent))rect=ProjectMember(rect,parent,false);
     memberCoordinates.Add(address,rect);
     if(!grouping)continue;
     for(int axis=0;axis<2;axis++) {
      outer[axis]=Math.Min(outer[axis],Math.Min(rect[axis],rect[axis+2]));
      outer[axis+2]=Math.Max(outer[axis+2],Math.Max(rect[axis],rect[axis+2]));
     }
    }
    if(grouping)NativePageControlPreparation.Same(outer,after["group_rectangle"],"Planned group bounds differ from the exact original members.");
    else {
     var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
     foreach(string address in expectedTop)NativeMemory.Require(names.Add(Convert.ToString(original[address]["name"])),"Planned ungroup would create an ambiguous top-level name.");
    }
    foreach(object value in (IEnumerable)after["surviving_controls"]) {
     var row=Map(value);string address=Convert.ToString(row["complete"]);var source=original[address];
     NativePageControlPreparation.Same(source["name"],row["name"],"Planned group edit would rename an original member.");
     NativePageControlPreparation.Same(properties[address],row["properties"],"Planned group edit would modify original member properties.");
     int index=moved.IndexOf(address);
     if(index<0) {
      NativeMemory.Require(!row.ContainsKey("raw_DWORD60"),"Unmoved selection state is determined by the original history operation.");
      continue;
     }
     var projected=ProjectMember(memberCoordinates[address],outer,grouping);
     NativePageControlPreparation.Same(projected,row["rectangle"],"Planned member geometry differs from the verified native coordinate transform.");
     int flag=!grouping&&moved.Count==1?4:index==moved.Count-1?2:1;
     NativeMemory.Require(Num(row["raw_DWORD60"])==flag,"Planned member selection differs from the original command order.");
    }
    var views=new NativePageViewOperations.Api(api.Engine,api.Context,api.Shared.Project);
    IntPtr frame;
    NativeMemory.Require(views.Probe(doc,out frame)&&Object.Equals(views.ActiveFrame(frame)["exact_page_is_active"],true),
      "Activate the exact target page inside the Pro designer before the planned drawing command.");
   }
   void ValidateExpectedSurvivors() {
    var wanted=new Dictionary<string,Dictionary<string,object>>();
    foreach(var row in FlatSnapshot(before["forest"])) {
     string address=Convert.ToString(row["complete"]);
     if(!removed.Contains(address))wanted.Add(address,row);
    }
    bool planned=RequestsGroupCoordinateRoles(action);
    var seen=new HashSet<string>();
    foreach(object value in (IEnumerable)Map(action["after"])["surviving_controls"]) {
     var row=Map(value);
     string address=NativePageControlPreparation.Text(row,"complete");
     Dictionary<string,object> original;
     NativeMemory.Require(wanted.TryGetValue(address,out original)&&seen.Add(address),"Expected survivor is absent/deleted/repeated.");
     foreach(string key in new[]{"name","rectangle","properties"})
      NativeMemory.Require(row.ContainsKey(key),"Complete expected survivor field missing: "+key);
     NativeMemory.Require(row.ContainsKey("raw_DWORD60")||planned&&!moved.Contains(address),
       "Moved and legacy group survivors need their exact expected selection state.");
     var rect=Integers(row["rectangle"]);
     if(planned&&!moved.Contains(address))
      NativePageControlPreparation.Same(original["rectangle"],rect,"An unaffected control needs its exact original rectangle.");
     else {
      bool directed=planned&&Object.Equals(original["class"],"CDrawLine");
      NativeMemory.Require(rect.Count==4&&(directed?rect[2]!=rect[0]||rect[3]!=rect[1]:rect[2]>=rect[0]&&rect[3]>=rect[1]),
        "Expected survivor native rectangle is invalid.");
     }
    }
    NativeMemory.Require(seen.Count==wanted.Count,"Expected survivors must cover every retained original control, including untouched controls.");
    if(kind=="control-group") {
     var expected=Integers(Map(action["after"])["group_rectangle"]);
     NativeMemory.Require(expected.Count==4&&expected[2]>expected[0]&&expected[3]>expected[1],"Expected new group bounding rectangle must be nondegenerate.");
    }else {
     int[] rect=NativePageControlAbi.Rectangle(targets[0].Full);
     NativeMemory.Require(rect[2]>rect[0]&&rect[3]>rect[1],"Original selected group bounding rectangle is degenerate.");
    }
   }
    void PreflightIncoming(){
     var affected=new List<string>();foreach(Node node in targets)affected.Add(oldPaths[NativeMemory.Hex(node.Full)]);
     bool planned=RequestsGroupCoordinateRoles(action);
     if(planned)foreach(string address in moved)affected.Add(oldPaths[address]);
     foreach(object value in (IEnumerable)Map(before["reference_graph"])["edges"]){
      var e=Map(value);string source=Convert.ToString(e["source"]),target=Convert.ToString(e["target"]);
      bool targetCovered=affected.Exists(path=>DrawingUnder(target,path));
      bool sourceCovered=affected.Exists(path=>DrawingUnder(source,path));
      NativeMemory.Require(!targetCovered||sourceCovered,"Group/ungroup with external incoming consumers still requires their complete expected models and persistence adapter; no command entered.");
      foreach(string address in removed)NativeMemory.Require(!DrawingUnder(target,oldPaths[address])&&(!planned||source!=oldPaths[address]),
        "A native group scheduled for removal has registered references.");
     }
    }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){NativeMemory.Require(!disposed&&!applied,"Native drawing command is disposed/already entered.");NativePageControlPreparation.Same(before,DrawingCapture(api,references,action,profile),"Complete native drawing preimage changed before Apply.");lease.BeginApply(action);applied=true;for(int i=0;i<targets.Count;i++){NativeOperationTrace.BeforeMutation("native-drawing-programmatic-selection-"+i);select(view,targets[i].Full,i==0?0:1);}var actualSelection=DrawingSelection(api,view,doc);NativeMemory.Require(actualSelection.Count==targets.Count,"Native selected target count differs.");for(int i=0;i<targets.Count;i++)NativeMemory.Require(actualSelection[i]==targets[i].Full,"Native selected target order differs.");var exactSelected=new List<IntPtr>();foreach(Node node in targets)exactSelected.Add(node.Full);historyState.OriginalSelectionReturned(exactSelected);NativeOperationTrace.BeforeMutation("native-drawing-root-dirty");rootDirty(root,1);Marshal.WriteInt32(root,NativeLayout.Offset("document.compile_valid"),0);NativeOperationTrace.BeforeMutation("original-native-drawing-"+kind);command(view);historyState.OriginalCommandWithEmbeddedStoreReturned();NativeMemory.Require(api.View(doc)==view&&modified(doc)==1,"Original drawing command did not keep its document/view and dirty contract.");NativeOperationTrace.BeforeMutation("native-drawing-invalidate");invalidate(view,1);NativeOperationTrace.BeforeMutation("native-drawing-update");update(view);after=DrawingCapture(api,references,action,profile);VerifyAfter(after);lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"state_after",after},{"native_command",kind},{"selection_after_is_intentional",true},{"native_history_store_projection",historyState.Report()},{"root_save_called",false},{"full_persistence_acceptance_pending",true}};}
   void VerifyAfter(Dictionary<string,object> state){var old=FlatSnapshot(before["forest"]);var now=FlatSnapshot(state["forest"]);var byAddress=new Dictionary<string,Dictionary<string,object>>();foreach(var row in now)byAddress.Add(Convert.ToString(row["complete"]),row);var oldByAddress=new Dictionary<string,Dictionary<string,object>>();foreach(var row in old)oldByAddress.Add(Convert.ToString(row["complete"]),row);string created=null;foreach(var row in now)if(!oldByAddress.ContainsKey(Convert.ToString(row["complete"]))){NativeMemory.Require(kind=="control-group"&&created==null&&Convert.ToString(row["class"])=="CDrawCell","Original command created an unexpected native control.");created=Convert.ToString(row["complete"]);string createdName=Convert.ToString(row["name"]);NativeMemory.Require(createdName.Length>0&&Num(row["type_id"])==0x5039&&Convert.ToString(row["rtti"])==".?AVCDrawCell@@"&&Convert.ToString(row["owner_document"])==NativeMemory.Hex(doc),"Original group has no actual native name/class/document owner.");int sameName=0;foreach(var other in now)if(Convert.ToString(other["name"])==createdName)sameName++;NativeMemory.Require(sameName==1,"Original group name is ambiguous in its real document namespace.");string expectedPath=references.Path(page)+"."+createdName;int paths=0;foreach(object linkerValue in(IEnumerable)state["control_linkers"]){var linker=Map(linkerValue);if(Convert.ToString(linker["complete"])==created){NativeMemory.Require(Convert.ToString(linker["linker"])==expectedPath,"Original group logical ObjectPath differs from its actual document/name.");paths++;}}NativeMemory.Require(paths==1,"Original group has no unique native logical ObjectPath.");}NativeMemory.Require((kind=="control-group")== (created!=null),"Original group creation count differs.");var actualTop=new List<string>();foreach(object value in (IEnumerable)state["forest"])actualTop.Add(Convert.ToString(Map(value)["complete"]));var expected=new List<string>();foreach(string address in expectedTop)expected.Add(address=="$created"?created:address);NativePageControlPreparation.Same(expected,actualTop,"Original command's exact top-level order differs.");
    Dictionary<string,Dictionary<string,object>> declared=new Dictionary<string,Dictionary<string,object>>();if(kind!="control-layer")foreach(object value in (IEnumerable)Map(action["after"])["surviving_controls"]){var row=Map(value);string address=Convert.ToString(row["complete"]);NativeMemory.Require(oldByAddress.ContainsKey(address)&&!removed.Contains(address)&&!declared.ContainsKey(address),"Declared survivor is not one distinct retained original control.");declared.Add(address,row);}foreach(var row in old){string address=Convert.ToString(row["complete"]);if(removed.Contains(address)){NativeMemory.Require(!byAddress.ContainsKey(address),"Removed group remains in the native tree.");continue;}Dictionary<string,object> actual;NativeMemory.Require(byAddress.TryGetValue(address,out actual),"An original retained control vanished.");var left=Map(historyState.AfterStoreSnapshot(row));var right=new Dictionary<string,object>(actual);left.Remove("path");right.Remove("path");left.Remove("children");right.Remove("children");if(kind=="control-layer"){if(address==NativeMemory.Hex(targets[0].Full))left["raw_DWORD60"]=4U;NativePageControlPreparation.Same(ChildAddresses(row),ChildAddresses(actual),"Layering altered a native group membership.");}else{Dictionary<string,object> proposed;NativeMemory.Require(declared.TryGetValue(address,out proposed),"Complete survivor expectation is missing.");left["name"]=proposed["name"];left["rectangle"]=proposed["rectangle"];object flags;if(proposed.TryGetValue("raw_DWORD60",out flags))left["raw_DWORD60"]=flags;NativePageControlPreparation.Same(ChildAddresses(row),ChildAddresses(actual),"Original group/ungroup altered a retained nested group membership.");}NativePageControlPreparation.Same(left,right,"Original native command changed a control beyond declared hierarchy/geometry/selection.");}
    var propertyMap=new Dictionary<string,object>();foreach(object value in (IEnumerable)state["control_properties"]){var row=Map(value);propertyMap.Add(Convert.ToString(row["complete"]),row["properties"]);}foreach(object value in (IEnumerable)before["control_properties"]){var row=Map(value);string address=Convert.ToString(row["complete"]);if(removed.Contains(address))continue;object expectedProperties=kind=="control-layer"?row["properties"]:declared[address]["properties"];NativePageControlPreparation.Same(expectedProperties,propertyMap[address],"Original command changed native declared properties beyond the complete expected survivor model.");}NativePageControlPreparation.Same(Map(before["page"])["attributes"],Map(state["page"])["attributes"],"Drawing command altered page attributes.");NativePageControlPreparation.Same(Map(before["page"])["pages"],Map(state["page"])["pages"],"Drawing command altered page IDs/names.");if(kind=="control-group"){NativePageControlPreparation.Same(Map(action["after"])["group_rectangle"],byAddress[created]["rectangle"],"Original new group bounding rectangle differs from its declared expected geometry.");NativeMemory.Require(Convert.ToUInt32(byAddress[created]["raw_DWORD60"])==4,"Original new group is not the exact native single selection.");var children=ChildAddresses(byAddress[created]);NativePageControlPreparation.Same(moved,children,"Original group did not move exactly the original doc-ordered immediate children.");}VerifyGraph(state);}
    void VerifyGraph(Dictionary<string,object> state){var paths=new Dictionary<string,string>();foreach(object value in (IEnumerable)state["control_linkers"]){var row=Map(value);paths.Add(Convert.ToString(row["complete"]),Convert.ToString(row["linker"]));}if(RequestsGroupCoordinateRoles(action))foreach(var row in oldPaths)if(!removed.Contains(row.Key))NativeMemory.Require(paths[row.Key]==row.Value,"Original group command changed a retained object's registered page-scoped linker.");var expected=new List<string>();foreach(object value in (IEnumerable)Map(before["reference_graph"])["edges"]){var row=Map(value);string source=Convert.ToString(row["source"]),target=Convert.ToString(row["target"]);source=DrawingReplace(source,paths);target=DrawingReplace(target,paths);expected.Add(source+"\u0000"+target);}var actual=new List<string>();foreach(object value in (IEnumerable)Map(state["reference_graph"])["edges"]){var row=Map(value);actual.Add(Convert.ToString(row["source"])+"\u0000"+Convert.ToString(row["target"]));}expected.Sort(StringComparer.Ordinal);actual.Sort(StringComparer.Ordinal);NativePageControlPreparation.Same(expected,actual,"Original drawing command changed the complete registered native edge graph beyond exact moved paths.");}
   string DrawingReplace(string value,Dictionary<string,string> paths){string old=null,newPath=null;foreach(var row in oldPaths)if(paths.ContainsKey(row.Key)&&DrawingUnder(value,row.Value)&&(old==null||row.Value.Length>old.Length)){old=row.Value;newPath=paths[row.Key];}return old==null?value:newPath+value.Substring(old.Length);}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!disposed,"Native drawing Apply must precede Flush.");lease.BeginFlush(action);var current=DrawingCapture(api,references,action,profile);VerifyAfter(current);int dirty=modified(doc);NativeMemory.Require(dirty==0||dirty==1,"Native page dirty representation differs.");if(dirty==1){NativeOperationTrace.BeforeMutation("native-drawing-page-save-data");NativeMemory.Require(save(api.Context.WindowService,page)&&modified(doc)==0,"Native drawing page SaveData failed its clean contract.");}lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false},{"full_persistence_acceptance_pending",true}};}
   public void Dispose(){disposed=true;}
  }
  static bool DrawingUnder(string value,string path){return value==path||value.StartsWith(path+".",StringComparison.Ordinal);}
 }
}
